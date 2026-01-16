"""Reddit video factory - Main orchestration module.

This module coordinates the entire pipeline:
1. Fetch Reddit thread data
2. Render title and comment cards as images (with optional word-by-word animation)
3. Generate TTS audio for each text segment (capturing word timings when possible)
4. Create or use background video
5. Assemble final video with ffmpeg

Optimizations:
- Caching for fonts and duration probes
- Optimized PNG compression
- Better error handling and validation
- Word-by-word text animation synchronized with TTS audio
"""
from __future__ import annotations
import json
import os
from typing import Any, List, Optional, Tuple

from ..config import FactoryConfig
from ..reddit_fetcher import extract_thread_id, fetch_thread, RedditComment
from ..render_cards import render_title_card, render_comment_card
from ..tts import tts_to_mp3, tts_to_mp3_with_word_timings, TTSOptions
from ..background import generate_background_mp4
from ..builder import concat_audio, render_video, probe_duration
from ..logger import get_logger

logger = get_logger(__name__)

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
        comments: List[RedditComment],
        target_duration: float,
        tts_opts: TTSOptions,
        mp3_dir: str,
        capture_word_timings: bool = False
    ) -> Tuple[List[RedditComment], List[str], List[List]]:
        """Select comments that fit within the target duration.
        
        Generates TTS for comments incrementally until the cumulative audio
        duration would exceed ``target_duration``. Returns a tuple
        ``(selected_comments, mp3_paths, word_timings_list)`` where:
        
        - ``selected_comments`` is a list of the comment objects that were
          successfully processed and kept.
        - ``mp3_paths`` is a list of paths to the corresponding generated MP3
          files, in the same order and of the same length as
          ``selected_comments``.
        - ``word_timings_list`` is a list of word timing lists (one per comment),
          only populated if capture_word_timings is True.
        
        Edge cases:
        
        - If ``comments`` is empty, or if TTS generation fails for every
          comment, all returned lists will be empty.
        - If adding a comment would exceed ``target_duration``, that comment is
          normally skipped and its MP3 file (if just generated) is removed.
        - However, if the very first successfully generated comment would
          exceed ``target_duration`` (including when ``target_duration`` is
          zero or negative), that first comment is still included so that at
          least one comment is returned when possible.
        - When TTS generation fails for a comment, the loop continues to the
          next comment. This creates gaps in MP3 file numbering (e.g., if
          comment 2 fails, there's no 2.mp3 but there is 3.mp3).
        
        This function never raises on individual TTS failures; such failures
        are logged as warnings and the corresponding comments are skipped.
        """
        # Handle edge case of non-positive target duration
        if target_duration <= 0:
            logger.warning("target_duration is zero or negative")
        
        selected = []
        mp3_paths = []
        word_timings_list = []
        cumulative_duration = 0.0
        
        for i, comment in enumerate(comments):
            # Generate TTS for this comment with original index to avoid duplicates
            # Note: Failed TTS generations will create gaps in numbering
            mp3_path = os.path.join(mp3_dir, f"{i}.mp3")
            try:
                if capture_word_timings:
                    word_timings = tts_to_mp3_with_word_timings(comment.body, mp3_path, tts_opts)
                else:
                    tts_to_mp3(comment.body, mp3_path, tts_opts)
                    word_timings = []
                
                duration = probe_duration(mp3_path)
                
                # Check if adding this comment would exceed target
                if cumulative_duration + duration > target_duration:
                    # If this is the first comment, include it anyway
                    if not selected:
                        selected.append(comment)
                        mp3_paths.append(mp3_path)
                        word_timings_list.append(word_timings)
                    else:
                        # Remove the file we just created since we won't use it
                        try:
                            os.remove(mp3_path)
                        except Exception:
                            pass
                    break
                
                selected.append(comment)
                mp3_paths.append(mp3_path)
                word_timings_list.append(word_timings)
                cumulative_duration += duration
                
            except Exception as e:
                logger.warning(f"Failed to generate TTS for comment {i}: {e}")
                continue
        
        return selected, mp3_paths, word_timings_list

    def make_from_url(self, url_or_id: str, keep_temp: bool=False) -> str:
        """Generate a Reddit video from a thread URL or ID.
        
        Main pipeline: fetch → render cards → TTS → background → assemble.
        Includes proper error handling and resource cleanup.
        """
        if not url_or_id:
            raise ValueError("URL or thread ID is required")
            
        tid = extract_thread_id(url_or_id)
        logger.info(f"Fetching thread: {tid}")
        
        # Determine target duration based on video_duration config
        duration_cfg = self.cfg.settings.video_duration
        if duration_cfg.mode == "long":
            target_duration = duration_cfg.long_duration_seconds
        else:
            target_duration = duration_cfg.target_duration_seconds
        
        logger.info(f"Target video duration: {target_duration}s ({duration_cfg.mode} mode)")
        
        # Fetch with potentially more comments for duration targeting
        # For long mode, estimate required comment count from target duration,
        # assuming an average of ~10 seconds of audio per comment.
        if duration_cfg.mode == "long":
            estimated_seconds_per_comment = 10
            estimated_needed_comments = max(1, int(target_duration / estimated_seconds_per_comment))
            fetch_max_comments = max(self.cfg.settings.max_comments, estimated_needed_comments)
        else:
            fetch_max_comments = self.cfg.settings.max_comments
        
        thread = fetch_thread(
            thread_id=tid,
            user_agent=self.cfg.reddit.user_agent,
            max_comments=fetch_max_comments,
            prefer_top=self.cfg.reddit.prefer_top_comments,
        )
        
        if not thread.title:
            raise ValueError("Thread has no title")
        if not thread.comments:
            logger.warning("No comments found in thread")

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

        # 1) Render cards with word-by-word animation if enabled
        logger.info("Rendering cards...")
        tts_opts = TTSOptions(
            engine=self.cfg.settings.voice.engine,
            edge_voice=self.cfg.settings.voice.edge_voice,
            rate=self.cfg.settings.voice.rate,
            volume=self.cfg.settings.voice.volume,
        )

        # 2) Generate TTS for title with word timings
        logger.info("Generating TTS audio...")
        title_mp3 = f"{mp3_dir}/title.mp3"
        
        if self.cfg.settings.word_by_word_animation:
            # Use word timing capture
            from ..render_progressive import render_progressive_title_cards
            title_word_timings = tts_to_mp3_with_word_timings(thread.title, title_mp3, tts_opts)
            # Generate progressive title cards
            title_cards_info = render_progressive_title_cards(
                thread.title,
                f"r/{thread.subreddit}",
                title_word_timings,
                png_dir,
                "title"
            )
        else:
            # Traditional single card rendering
            tts_to_mp3(thread.title, title_mp3, tts_opts)
            title_img = render_title_card(thread.title, f"r/{thread.subreddit}")
            title_png = f"{png_dir}/title.png"
            title_img.save(title_png, optimize=keep_temp)
            title_duration = probe_duration(title_mp3)
            title_cards_info = [(title_png, title_duration)]
        
        # Estimate how much time we have for comments
        title_duration = probe_duration(title_mp3)
        remaining_duration = max(0, target_duration - title_duration)
        
        # Select comments to fit target duration, but handle case where title
        # already consumes or exceeds the target duration
        if remaining_duration <= 0:
            logger.warning(
                "Title duration meets or exceeds target duration; no comments will be added"
            )
            selected_comments = []
            comment_mp3s = []
            comment_word_timings_list = []
            all_comment_cards_info = []
        else:
            selected_comments, comment_mp3s, comment_word_timings_list = self._select_comments_for_duration(
                thread.comments, 
                remaining_duration, 
                tts_opts, 
                mp3_dir,
                capture_word_timings=self.cfg.settings.word_by_word_animation
            )
            
            logger.info(f"Selected {len(selected_comments)} comments for target duration")
            
            # Render comment cards (with or without word-by-word animation)
            all_comment_cards_info: List[List[Tuple[str, float]]] = []
            
            if self.cfg.settings.word_by_word_animation:
                from ..render_progressive import render_progressive_comment_cards
                for i, c in enumerate(selected_comments):
                    # Use already-captured word timings
                    comment_word_timings = comment_word_timings_list[i]
                    # Generate progressive comment cards
                    comment_cards = render_progressive_comment_cards(
                        c.author,
                        c.body,
                        c.score,
                        comment_word_timings,
                        png_dir,
                        f"comment_{i}"
                    )
                    all_comment_cards_info.append(comment_cards)
            else:
                # Traditional single card per comment
                for i, c in enumerate(selected_comments):
                    img = render_comment_card(c.author, c.body, c.score)
                    p = os.path.join(png_dir, f"comment_{i}.png")
                    img.save(p, optimize=keep_temp)
                    duration = probe_duration(comment_mp3s[i])
                    all_comment_cards_info.append([(p, duration)])

        # 3) Background
        logger.info("Preparing background...")
        bg_cfg = self.cfg.settings.background
        bg_mp4 = f"{temp_dir}/background.mp4"
        if bg_cfg.background_path:
            import shutil
            shutil.copyfile(bg_cfg.background_path, bg_mp4)
            logger.debug(f"Using background from: {bg_cfg.background_path}")
        else:
            if bg_cfg.auto_generate_background:
                seconds = float(bg_cfg.background_seconds or 600)
                logger.debug(f"Generating background video ({seconds}s)")
                generate_background_mp4(
                    bg_mp4,
                    self.cfg.settings.resolution_w,
                    self.cfg.settings.resolution_h,
                    seconds=seconds,
                    style=bg_cfg.style,
                )
            else:
                raise FileNotFoundError("No background provided and auto_generate_background=false")

        # Optional background audio mp3 (user can drop a file here)
        bg_mp3 = f"{temp_dir}/background.mp3"
        bg_audio_path = bg_mp3 if os.path.exists(bg_mp3) else None

        # 4) Assemble
        logger.info("Assembling final video...")
        audio_mp3 = f"{temp_dir}/audio.mp3"
        audio_paths = [title_mp3] + comment_mp3s
        concat_audio(audio_paths, audio_mp3)

        # Flatten all progressive cards into a single list with durations
        images: List[str] = []
        durations: List[float] = []
        
        # Add title cards
        for img_path, dur in title_cards_info:
            images.append(img_path)
            durations.append(dur)
        
        # Add comment cards
        for comment_cards in all_comment_cards_info:
            for img_path, dur in comment_cards:
                images.append(img_path)
                durations.append(dur)

        out_dir = f"results/{thread.subreddit}"
        _ensure_dir(out_dir)
        out_mp4 = os.path.join(out_dir, _sanitize_filename(thread.title)[:120] + ".mp4")

        screenshot_width = int((self.cfg.settings.resolution_w * 45) // 100)
        
        logger.debug(f"Output file: {out_mp4}")
        logger.debug(f"Total audio duration: {sum(durations):.2f}s")
        logger.debug(f"Images count: {len(images)}")

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
            logger.debug(f"Temporary files cleaned up: {temp_dir}")

        return out_mp4

# Exports for package
__all__ = ["RedditVideoFactory", "FactoryConfig"]

