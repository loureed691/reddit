"""Reddit video factory - Main orchestration module.

This module coordinates the entire pipeline:
1. Fetch Reddit thread data
2. Render title and comment cards as images (or use word-by-word captions)
3. Generate TTS audio for each text segment with word timestamps
4. Create or use background video
5. Assemble final video with ffmpeg

Optimizations:
- Caching for fonts and duration probes
- Optimized PNG compression
- Better error handling and validation
- Word-by-word caption sync for viral content
"""
from __future__ import annotations
import json
import os
from typing import Any, List, Optional, Tuple

from ..config import FactoryConfig
from ..reddit_fetcher import extract_thread_id, fetch_thread, RedditComment
from ..render_cards import render_title_card, render_comment_card
from ..tts import tts_to_mp3, tts_to_mp3_with_timestamps, TTSOptions, WordTimestamp
from ..background import generate_background_mp4
from ..builder import concat_audio, render_video, probe_duration
from ..word_captions import generate_word_captions_filter, save_word_timestamps_json
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
        mp3_dir: str
    ) -> Tuple[List[RedditComment], List[str]]:
        """Select comments that fit within the target duration.
        
        Generates TTS for comments incrementally until the cumulative audio
        duration would exceed ``target_duration``. Returns a tuple
        ``(selected_comments, mp3_paths)`` where:
        
        - ``selected_comments`` is a list of the comment objects that were
          successfully processed and kept.
        - ``mp3_paths`` is a list of paths to the corresponding generated MP3
          files, in the same order and of the same length as
          ``selected_comments``.
        
        Edge cases:
        
        - If ``comments`` is empty, or if TTS generation fails for every
          comment, both returned lists will be empty.
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
        cumulative_duration = 0.0
        
        for i, comment in enumerate(comments):
            # Generate TTS for this comment with original index to avoid duplicates
            # Note: Failed TTS generations will create gaps in numbering
            mp3_path = os.path.join(mp3_dir, f"{i}.mp3")
            try:
                tts_to_mp3(comment.body, mp3_path, tts_opts)
                duration = probe_duration(mp3_path)
                
                # Check if adding this comment would exceed target
                if cumulative_duration + duration > target_duration:
                    # If this is the first comment, include it anyway
                    if not selected:
                        selected.append(comment)
                        mp3_paths.append(mp3_path)
                    else:
                        # Remove the file we just created since we won't use it
                        try:
                            os.remove(mp3_path)
                        except Exception:
                            pass
                    break
                
                selected.append(comment)
                mp3_paths.append(mp3_path)
                cumulative_duration += duration
                
            except Exception as e:
                logger.warning(f"Failed to generate TTS for comment {i}: {e}")
                continue
        
        return selected, mp3_paths

    def _select_comments_for_duration_with_timestamps(
        self, 
        comments: List[RedditComment],
        target_duration: float,
        tts_opts: TTSOptions,
        mp3_dir: str,
        timestamps_dir: str
    ) -> Tuple[List[RedditComment], List[str], List[List[WordTimestamp]]]:
        """Select comments with word-level timestamps.
        
        Similar to _select_comments_for_duration but also extracts word timestamps.
        
        Returns:
            Tuple of (selected_comments, mp3_paths, word_timestamps_list)
            where word_timestamps_list[i] contains word timestamps for comment i.
        """
        # Handle edge case of non-positive target duration
        if target_duration <= 0:
            logger.warning("target_duration is zero or negative")
        
        selected = []
        mp3_paths = []
        all_word_timestamps = []
        cumulative_duration = 0.0
        
        for i, comment in enumerate(comments):
            mp3_path = os.path.join(mp3_dir, f"{i}.mp3")
            try:
                # Generate TTS with word timestamps
                word_timestamps = tts_to_mp3_with_timestamps(comment.body, mp3_path, tts_opts)
                duration = probe_duration(mp3_path)
                
                # Save timestamps to JSON for debugging
                if word_timestamps:
                    timestamps_json = os.path.join(timestamps_dir, f"{i}_timestamps.json")
                    save_word_timestamps_json(word_timestamps, timestamps_json)
                
                # Check if adding this comment would exceed target
                if cumulative_duration + duration > target_duration:
                    # If this is the first comment, include it anyway
                    if not selected:
                        selected.append(comment)
                        mp3_paths.append(mp3_path)
                        all_word_timestamps.append(word_timestamps)
                    else:
                        # Remove the file we just created since we won't use it
                        try:
                            os.remove(mp3_path)
                        except Exception:
                            pass
                    break
                
                selected.append(comment)
                mp3_paths.append(mp3_path)
                all_word_timestamps.append(word_timestamps)
                cumulative_duration += duration
                
            except Exception as e:
                logger.warning(f"Failed to generate TTS for comment {i}: {e}")
                continue
        
        return selected, mp3_paths, all_word_timestamps

    def make_from_url(self, url_or_id: str, keep_temp: bool=False) -> str:
        """Generate a Reddit video from a thread URL or ID.
        
        Main pipeline: fetch → render cards → TTS → background → assemble.
        Supports both static card overlays and word-by-word captions.
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
        
        # Check if word captions are enabled
        word_captions_enabled = self.cfg.settings.word_captions.enabled
        logger.info(f"Word-by-word captions: {'enabled' if word_captions_enabled else 'disabled'}")
        
        # Fetch with potentially more comments for duration targeting
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
        timestamps_dir = f"{temp_dir}/timestamps"
        _ensure_dir(png_dir)
        _ensure_dir(mp3_dir)
        if word_captions_enabled:
            _ensure_dir(timestamps_dir)

        _safe_write_json(f"{temp_dir}/thread.json", {
            "thread_id": thread.thread_id,
            "subreddit": thread.subreddit,
            "title": thread.title,
            "comments": [{"author": c.author, "score": c.score, "body": c.body} for c in thread.comments],
        })

        # TTS options
        tts_opts = TTSOptions(
            engine=self.cfg.settings.voice.engine,
            edge_voice=self.cfg.settings.voice.edge_voice,
            rate=self.cfg.settings.voice.rate,
            volume=self.cfg.settings.voice.volume,
        )

        # Generate TTS for title
        logger.info("Generating TTS audio...")
        title_mp3 = f"{mp3_dir}/title.mp3"
        
        if word_captions_enabled:
            # Generate with timestamps
            title_timestamps = tts_to_mp3_with_timestamps(thread.title, title_mp3, tts_opts)
            if title_timestamps:
                save_word_timestamps_json(
                    title_timestamps,
                    os.path.join(timestamps_dir, "title_timestamps.json")
                )
        else:
            # Generate without timestamps
            tts_to_mp3(thread.title, title_mp3, tts_opts)
            title_timestamps = []
        
        # Estimate how much time we have for comments
        title_duration = probe_duration(title_mp3)
        remaining_duration = max(0, target_duration - title_duration)
        
        # Select comments to fit target duration
        if remaining_duration <= 0:
            logger.warning(
                "Title duration meets or exceeds target duration; no comments will be added"
            )
            selected_comments = []
            comment_mp3s = []
            comment_timestamps_list = []
        else:
            if word_captions_enabled:
                selected_comments, comment_mp3s, comment_timestamps_list = \
                    self._select_comments_for_duration_with_timestamps(
                        thread.comments, remaining_duration, tts_opts, mp3_dir, timestamps_dir
                    )
            else:
                selected_comments, comment_mp3s = self._select_comments_for_duration(
                    thread.comments, remaining_duration, tts_opts, mp3_dir
                )
                comment_timestamps_list = []
        
        logger.info(f"Selected {len(selected_comments)} comments for target duration")

        # Render cards (still needed for fallback or when word captions disabled)
        logger.info("Rendering cards...")
        title_img = render_title_card(thread.title, f"r/{thread.subreddit}")
        title_png = f"{png_dir}/title.png"
        title_img.save(title_png, optimize=keep_temp)

        comment_pngs: List[str] = []
        for i, c in enumerate(selected_comments):
            img = render_comment_card(c.author, c.body, c.score)
            p = os.path.join(png_dir, f"comment_{i}.png")
            img.save(p, optimize=keep_temp)
            comment_pngs.append(p)

        # Background
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

        # Optional background audio mp3
        bg_mp3 = f"{temp_dir}/background.mp3"
        bg_audio_path = bg_mp3 if os.path.exists(bg_mp3) else None

        # Assemble
        logger.info("Assembling final video...")
        audio_mp3 = f"{temp_dir}/audio.mp3"
        audio_paths = [title_mp3] + comment_mp3s
        concat_audio(audio_paths, audio_mp3)

        durations = [probe_duration(title_mp3)] + [probe_duration(p) for p in comment_mp3s]
        images = [title_png] + comment_pngs

        out_dir = f"results/{thread.subreddit}"
        _ensure_dir(out_dir)
        out_mp4 = os.path.join(out_dir, _sanitize_filename(thread.title)[:120] + ".mp4")

        screenshot_width = int((self.cfg.settings.resolution_w * 45) // 100)
        
        logger.debug(f"Output file: {out_mp4}")
        logger.debug(f"Total audio duration: {sum(durations):.2f}s")
        logger.debug(f"Images count: {len(images)}")

        # Generate word captions filter if enabled
        word_captions_filter = None
        if word_captions_enabled and (title_timestamps or any(comment_timestamps_list)):
            logger.info("Generating word-by-word caption filters...")
            
            # Combine all word timestamps with time offsets
            all_word_timestamps = []
            cumulative_time = 0.0
            
            # Add title word timestamps
            for wt in title_timestamps:
                all_word_timestamps.append(
                    WordTimestamp(
                        word=wt.word,
                        start_ms=wt.start_ms + cumulative_time,
                        end_ms=wt.end_ms + cumulative_time,
                    )
                )
            cumulative_time += title_duration * 1000  # Convert to ms
            
            # Add comment word timestamps
            for i, comment_timestamps in enumerate(comment_timestamps_list):
                for wt in comment_timestamps:
                    all_word_timestamps.append(
                        WordTimestamp(
                            word=wt.word,
                            start_ms=wt.start_ms + cumulative_time,
                            end_ms=wt.end_ms + cumulative_time,
                        )
                    )
                # Add this comment's duration for the next iteration
                # durations = [title_duration, comment0_duration, comment1_duration, ...]
                # So comment i's duration is at durations[i + 1]
                cumulative_time += durations[i + 1] * 1000  # Convert to ms
            
            # Generate filter string
            caption_cfg = self.cfg.settings.word_captions
            y_position = int(self.cfg.settings.resolution_h * caption_cfg.y_position_percent)
            
            word_captions_filter = generate_word_captions_filter(
                all_word_timestamps,
                video_width=self.cfg.settings.resolution_w,
                video_height=self.cfg.settings.resolution_h,
                font_size=caption_cfg.font_size,
                font_color=caption_cfg.font_color,
                border_color=caption_cfg.border_color,
                border_width=caption_cfg.border_width,
                y_position=y_position,
            )
            
            logger.debug(f"Generated caption filter for {len(all_word_timestamps)} words")

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
            word_captions_filter=word_captions_filter,
        )

        if not keep_temp:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Temporary files cleaned up: {temp_dir}")

        return out_mp4

# Exports for package
__all__ = ["RedditVideoFactory", "FactoryConfig"]

