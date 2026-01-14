"""Reddit video factory - Main orchestration module.

This module coordinates the entire pipeline:
1. Fetch Reddit thread data
2. Render title and comment cards as images
3. Generate TTS audio for each text segment
4. Create or use background video
5. Assemble final video with ffmpeg

Optimizations:
- Caching for fonts and duration probes
- Optimized PNG compression
- Better error handling and validation
"""
from __future__ import annotations
import json
import os
from typing import Any, List, Optional

from rich.console import Console

from ..config import FactoryConfig
from ..reddit_fetcher import extract_thread_id, fetch_thread
from ..render_cards import render_title_card, render_comment_card
from ..tts import tts_to_mp3, TTSOptions
from ..background import generate_background_mp4
from ..builder import concat_audio, render_video, probe_duration

console = Console()

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _safe_write_json(path: str, obj: Any) -> None:
    _ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _sanitize_folder(s: str) -> str:
    import re
    return re.sub(r"[^\w\s-]", "", s or "").strip() or "thread"

def _sanitize_filename(s: str) -> str:
    import re
    s = re.sub(r'[?\\"%*:|<>]', "", (s or "video"))
    s = re.sub(r"\s+", " ", s).strip()
    return s or "video"

class RedditVideoFactory:
    def __init__(self, cfg: FactoryConfig):
        self.cfg = cfg

    def _select_comments_for_duration(
        self, 
        comments: List,
        target_duration: float,
        tts_opts: TTSOptions,
        mp3_dir: str
    ) -> tuple:
        """Select comments that fit within the target duration.
        
        Generates TTS for comments incrementally until target duration is reached.
        Returns tuple of (selected_comments, mp3_paths).
        """
        selected = []
        mp3_paths = []
        cumulative_duration = 0.0
        
        for i, comment in enumerate(comments):
            # Generate TTS for this comment with sequential index
            mp3_path = f"{mp3_dir}/{len(selected)}.mp3"
            try:
                tts_to_mp3(comment.body, mp3_path, tts_opts)
                duration = probe_duration(mp3_path)
                
                # Check if adding this comment would exceed target
                if cumulative_duration + duration > target_duration:
                    # If this is the first comment, include it anyway
                    if len(selected) == 0:
                        selected.append(comment)
                        mp3_paths.append(mp3_path)
                    else:
                        # Remove the file we just created since we won't use it
                        import os
                        try:
                            os.remove(mp3_path)
                        except Exception:
                            pass
                    break
                
                selected.append(comment)
                mp3_paths.append(mp3_path)
                cumulative_duration += duration
                
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to generate TTS for comment {i}: {e}[/yellow]")
                continue
        
        return selected, mp3_paths

    def make_from_url(self, url_or_id: str, keep_temp: bool=False) -> str:
        """Generate a Reddit video from a thread URL or ID.
        
        Main pipeline: fetch → render cards → TTS → background → assemble.
        Includes proper error handling and resource cleanup.
        """
        if not url_or_id:
            raise ValueError("URL or thread ID is required")
            
        tid = extract_thread_id(url_or_id)
        console.print(f"[bold cyan]Fetching thread: {tid}[/bold cyan]")
        
        # Determine target duration based on video_duration config
        duration_cfg = self.cfg.settings.video_duration
        if duration_cfg.mode == "long":
            target_duration = duration_cfg.long_duration_seconds
        else:
            target_duration = duration_cfg.target_duration_seconds
        
        console.print(f"[cyan]Target video duration: {target_duration}s ({duration_cfg.mode} mode)[/cyan]")
        
        # Fetch with potentially more comments for duration targeting
        fetch_max_comments = max(self.cfg.settings.max_comments, 100) if duration_cfg.mode == "long" else self.cfg.settings.max_comments
        
        thread = fetch_thread(
            thread_id=tid,
            user_agent=self.cfg.reddit.user_agent,
            max_comments=fetch_max_comments,
            prefer_top=self.cfg.reddit.prefer_top_comments,
        )
        
        if not thread.title:
            raise ValueError("Thread has no title")
        if not thread.comments:
            console.print("[yellow]Warning: No comments found in thread[/yellow]")

        reddit_id = _sanitize_folder(thread.thread_id)
        temp_dir = f"assets/temp/{reddit_id}"
        png_dir = f"{temp_dir}/png"
        mp3_dir = f"{temp_dir}/mp3"
        _ensure_dir(png_dir)
        _ensure_dir(mp3_dir)

        _safe_write_json(f"{temp_dir}/thread.json", {
            "thread_id": thread.thread_id,
            "subreddit": thread.subreddit,
            "title": thread.title,
            "comments": [{"author": c.author, "score": c.score, "body": c.body} for c in thread.comments],
        })

        # 1) Render cards
        console.print("[bold]Rendering cards…[/bold]")
        title_img = render_title_card(thread.title, f"r/{thread.subreddit}")
        title_png = f"{png_dir}/title.png"
        # Only optimize PNGs if keeping temp files, otherwise it's wasted time
        title_img.save(title_png, optimize=keep_temp)

        # 2) TTS for title first to estimate duration
        console.print("[bold]Generating TTS…[/bold]")
        tts_opts = TTSOptions(
            engine=self.cfg.settings.voice.engine,
            edge_voice=self.cfg.settings.voice.edge_voice,
            rate=self.cfg.settings.voice.rate,
            volume=self.cfg.settings.voice.volume,
        )

        title_mp3 = f"{mp3_dir}/title.mp3"
        tts_to_mp3(thread.title, title_mp3, tts_opts)
        
        # Estimate how much time we have for comments
        title_duration = probe_duration(title_mp3)
        remaining_duration = max(0, target_duration - title_duration)
        
        # Select comments to fit target duration
        selected_comments, comment_mp3s = self._select_comments_for_duration(
            thread.comments, remaining_duration, tts_opts, mp3_dir
        )
        
        console.print(f"[cyan]Selected {len(selected_comments)} comments for target duration[/cyan]")

        comment_pngs: List[str] = []
        for i, c in enumerate(selected_comments):
            img = render_comment_card(c.author, c.body, c.score)
            p = f"{png_dir}/comment_{i}.png"
            img.save(p, optimize=keep_temp)
            comment_pngs.append(p)

        # 3) Background
        console.print("[bold]Preparing background…[/bold]")
        bg_cfg = self.cfg.settings.background
        bg_mp4 = f"{temp_dir}/background.mp4"
        if bg_cfg.background_path:
            import shutil
            shutil.copyfile(bg_cfg.background_path, bg_mp4)
        else:
            if bg_cfg.auto_generate_background:
                seconds = float(bg_cfg.background_seconds or 600)
                generate_background_mp4(
                    bg_mp4,
                    self.cfg.settings.resolution_w,
                    self.cfg.settings.resolution_h,
                    seconds=seconds,
                )
            else:
                raise FileNotFoundError("No background provided and auto_generate_background=false")

        # Optional background audio mp3 (user can drop a file here)
        bg_mp3 = f"{temp_dir}/background.mp3"
        bg_audio_path = bg_mp3 if os.path.exists(bg_mp3) else None

        # 4) Assemble
        console.print("[bold]Assembling final video…[/bold]")
        audio_mp3 = f"{temp_dir}/audio.mp3"
        audio_paths = [title_mp3] + comment_mp3s
        concat_audio(audio_paths, audio_mp3)

        durations = [probe_duration(title_mp3)] + [probe_duration(p) for p in comment_mp3s]
        images = [title_png] + comment_pngs

        out_dir = f"results/{thread.subreddit}"
        _ensure_dir(out_dir)
        out_mp4 = os.path.join(out_dir, _sanitize_filename(thread.title)[:120] + ".mp4")

        screenshot_width = int((self.cfg.settings.resolution_w * 45) // 100)

        render_video(
            background_mp4=bg_mp4,
            out_mp4=out_mp4,
            audio_mp3=audio_mp3,
            image_paths=images,
            image_durations=durations,
            W=self.cfg.settings.resolution_w,
            H=self.cfg.settings.resolution_h,
            screenshot_width=screenshot_width,
            opacity=self.cfg.settings.opacity,
            bg_audio_mp3=bg_audio_path,
            bg_audio_volume=float(bg_cfg.background_audio_volume if bg_cfg.enable_extra_audio else 0.0),
        )

        if not keep_temp:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        return out_mp4

# Exports for package
__all__ = ["RedditVideoFactory", "FactoryConfig"]

