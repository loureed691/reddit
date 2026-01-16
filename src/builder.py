"""Video builder with ffmpeg integration and progress tracking.

Handles:
- Audio concatenation with proper codec settings
- Video overlay composition
- Progress tracking via background thread
- LRU caching for duration probes
- Optimized ffmpeg presets for faster encoding
"""
from __future__ import annotations
import multiprocessing
import os
import re
import subprocess
import tempfile
import threading
import time
from os.path import exists
from typing import Optional, List

import ffmpeg
from tqdm import tqdm

from .logger import get_logger

logger = get_logger(__name__)

class ProgressFfmpeg(threading.Thread):
    """Background thread to track ffmpeg progress via progress file.
    
    Optimized with less frequent polling and better resource cleanup.
    """
    def __init__(self, duration_seconds: float, cb):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.duration = max(0.001, float(duration_seconds))
        self.cb = cb
        tmp = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        self.progress_path = tmp.name
        tmp.close()
        self._last = 0.0

    def run(self):
        while not self.stop_event.is_set():
            sec = self._read_seconds()
            if sec is not None:
                p = max(self._last, min(1.0, sec / self.duration))
                self._last = p
                try:
                    self.cb(p)
                except Exception:
                    pass
            time.sleep(0.5)  # Poll every 500ms to balance responsiveness and CPU usage

    def _read_seconds(self) -> Optional[float]:
        try:
            if not exists(self.progress_path):
                return None
            with open(self.progress_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            ms = re.findall(r"out_time_ms=(\d+)", content)
            if ms:
                return int(ms[-1]) / 1_000_000.0
        except Exception:
            return None
        return None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop_event.set()
        self.join(timeout=2)
        try:
            os.remove(self.progress_path)
        except Exception:
            pass

from functools import lru_cache

@lru_cache(maxsize=128)
def probe_duration(path: str) -> float:
    """Probe media file duration with caching for repeated calls."""
    meta = ffmpeg.probe(path)
    dur = meta.get("format", {}).get("duration", None)
    try:
        return float(dur) if dur is not None else 0.0
    except Exception:
        return 0.0

def concat_audio(audio_paths: List[str], out_mp3: str) -> float:
    """Concatenate multiple audio files into one.
    
    Returns total duration and uses optimized ffmpeg settings.
    """
    if not audio_paths:
        raise ValueError("No audio paths provided for concatenation")
    
    logger.debug(f"Concatenating {len(audio_paths)} audio files")
    
    streams = [ffmpeg.input(p) for p in audio_paths]
    concat = ffmpeg.concat(*streams, a=1, v=0)
    (
        ffmpeg.output(concat, out_mp3, **{"b:a":"192k"})
        .overwrite_output()
        .run(quiet=True, capture_stderr=True)
    )
    total_duration = sum(max(0.0, probe_duration(p)) for p in audio_paths)
    logger.debug(f"Audio concatenated: {total_duration:.2f}s total duration")
    return total_duration

def merge_background_audio(audio_stream, bg_mp3: str, bg_volume: float):
    """Merge background audio with main audio stream.
    
    Uses amix filter with proper volume control.
    """
    if not bg_mp3 or bg_volume <= 0 or not exists(bg_mp3):
        return audio_stream
    bg = ffmpeg.input(bg_mp3).filter("volume", bg_volume)
    return ffmpeg.filter([audio_stream, bg], "amix", duration="longest")

def render_video(
    background_mp4: str,
    out_mp4: str,
    audio_mp3: str,
    image_paths: List[str],
    image_durations: List[float],
    W: int,
    H: int,
    screenshot_width: int,
    opacity: float,
    bg_audio_mp3: Optional[str] = None,
    bg_audio_volume: float = 0.0,
    word_captions_filter: Optional[str] = None,
):
    """Render final video with overlays and audio.
    
    Optimized with better ffmpeg presets and parallel processing.
    
    Args:
        word_captions_filter: Optional ffmpeg drawtext filter chain for word-by-word captions.
                             If provided, captions are overlaid on top of the Reddit cards.
    """
    if len(image_paths) != len(image_durations):
        raise ValueError("image_paths and image_durations mismatch")
    
    if not image_paths:
        raise ValueError("No images provided for video rendering")
    
    logger.info(f"Rendering video: {len(image_paths)} images, resolution {W}x{H}")
    logger.debug(f"Output: {out_mp4}")

    total_len = max(0.1, sum(max(0.0, d) for d in image_durations))
    logger.debug(f"Total video length: {total_len:.2f}s")

    # Always render with card overlays, optionally add word captions on top
    if word_captions_filter:
        _render_video_with_cards_and_word_captions(
            background_mp4=background_mp4,
            out_mp4=out_mp4,
            audio_mp3=audio_mp3,
            image_paths=image_paths,
            image_durations=image_durations,
            W=W,
            H=H,
            screenshot_width=screenshot_width,
            opacity=opacity,
            total_len=total_len,
            word_captions_filter=word_captions_filter,
            bg_audio_mp3=bg_audio_mp3,
            bg_audio_volume=bg_audio_volume,
        )
    else:
        _render_video_with_static_overlays(
            background_mp4=background_mp4,
            out_mp4=out_mp4,
            audio_mp3=audio_mp3,
            image_paths=image_paths,
            image_durations=image_durations,
            W=W,
            H=H,
            screenshot_width=screenshot_width,
            opacity=opacity,
            total_len=total_len,
            bg_audio_mp3=bg_audio_mp3,
            bg_audio_volume=bg_audio_volume,
        )

def _render_video_with_cards_and_word_captions(
    background_mp4: str,
    out_mp4: str,
    audio_mp3: str,
    image_paths: List[str],
    image_durations: List[float],
    W: int,
    H: int,
    screenshot_width: int,
    opacity: float,
    total_len: float,
    word_captions_filter: str,
    bg_audio_mp3: Optional[str] = None,
    bg_audio_volume: float = 0.0,
):
    """Render video with Reddit cards AND word-by-word captions on top."""
    logger.info("Rendering with Reddit cards + word-by-word captions")
    
    # Build complex filter that overlays cards, then adds word captions
    # Step 1: Scale background
    # Step 2: Overlay each card image at the right time
    # Step 3: Apply word caption drawtext filters on top
    
    # Start building filter complex
    filter_parts = []
    
    # Scale background
    filter_parts.append(f"[0:v]scale={W}:{H}[bg]")
    
    # Overlay cards one by one
    t = 0.0
    current_output = "bg"
    for idx, (img_path, duration) in enumerate(zip(image_paths, image_durations)):
        input_idx = idx + 2  # 0=background, 1=audio, 2+=images
        next_output = f"v{idx}" if idx < len(image_paths) - 1 else "cards"
        
        # Apply opacity to all except title (first card)
        if idx == 0:
            # Title card - no opacity
            filter_parts.append(
                f"[{input_idx}:v]scale={screenshot_width}:-1[img{idx}]"
            )
        else:
            # Comment cards - apply opacity
            filter_parts.append(
                f"[{input_idx}:v]scale={screenshot_width}:-1,colorchannelmixer=aa={opacity}[img{idx}]"
            )
        
        # Overlay this card
        filter_parts.append(
            f"[{current_output}][img{idx}]overlay="
            f"x=(main_w-overlay_w)/2:y=(main_h-overlay_h)/2:"
            f"enable='between(t,{t:.3f},{t+duration:.3f})'[{next_output}]"
        )
        
        current_output = next_output
        t += duration
    
    # Apply word captions on top of cards
    filter_parts.append(f"[cards]{word_captions_filter}[vout]")
    
    filter_complex = ";".join(filter_parts)
    
    # Build ffmpeg command with all image inputs
    cmd = [
        "ffmpeg",
        "-i", background_mp4,  # Input 0: background
        "-i", audio_mp3,       # Input 1: audio
    ]
    
    # Add all card images as inputs
    for img_path in image_paths:
        cmd.extend(["-i", img_path])
    
    # Add background audio if provided
    if bg_audio_mp3 and bg_audio_volume > 0 and os.path.exists(bg_audio_mp3):
        bg_audio_idx = len(image_paths) + 2
        cmd.extend(["-i", bg_audio_mp3])
        # Mix audio streams
        audio_filter = f"[1:a]volume=1.0[a1];[{bg_audio_idx}:a]volume={bg_audio_volume}[a2];[a1][a2]amix=duration=longest[aout]"
        cmd.extend(["-filter_complex", f"{filter_complex};{audio_filter}"])
        cmd.extend(["-map", "[vout]", "-map", "[aout]"])
    else:
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[vout]", "-map", "1:a"])
    
    # Output options
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "faster",
        "-b:v", "8M",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(total_len),
        "-movflags", "+faststart",
        "-threads", str(min(multiprocessing.cpu_count(), 8)),
        "-y",  # Overwrite output
        out_mp4
    ])
    
    logger.debug(f"FFmpeg command with {len(image_paths)} card overlays + word captions")
    
    # Run with progress tracking
    pbar = tqdm(total=100, desc="Encoding", unit="%", ncols=80)
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg failed with return code {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")
            raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")
        
        pbar.update(100)
        logger.info(f"Video rendered successfully: {out_mp4}")
    except Exception as e:
        logger.error(f"Failed to render video: {e}")
        raise
    finally:
        pbar.close()

def _render_video_with_static_overlays(
    background_mp4: str,
    out_mp4: str,
    audio_mp3: str,
    image_paths: List[str],
    image_durations: List[float],
    W: int,
    H: int,
    screenshot_width: int,
    opacity: float,
    total_len: float,
    bg_audio_mp3: Optional[str] = None,
    bg_audio_volume: float = 0.0,
):
    """Render video with static card overlays (original method)."""
    logger.info("Rendering with static card overlays")

    bg = ffmpeg.input(background_mp4)
    t = 0.0

    def overlay_center(base, img_path: str, start: float, dur: float, apply_opacity: bool):
        """Apply centered overlay with optional opacity."""
        v = ffmpeg.input(img_path)["v"].filter("scale", screenshot_width, -1)
        if apply_opacity:
            v = v.filter("colorchannelmixer", aa=opacity)
        return base.overlay(
            v,
            enable=f"between(t,{start},{start+dur})",
            x="(main_w-overlay_w)/2",
            y="(main_h-overlay_h)/2",
        )

    # Title + comments in order
    for i, (p, d) in enumerate(zip(image_paths, image_durations)):
        bg = overlay_center(bg, p, t, d, apply_opacity=(i != 0))
        t += d

    bg = bg.filter("scale", W, H)

    audio = ffmpeg.input(audio_mp3)
    final_audio = merge_background_audio(audio, bg_audio_mp3 or "", bg_audio_volume)

    pbar = tqdm(total=100, desc="Encoding", unit="%", ncols=80)
    def on_update(p: float):
        target = max(0.0, min(100.0, p*100))
        delta = target - pbar.n
        if delta > 0:
            pbar.update(delta)

    with ProgressFfmpeg(total_len, on_update) as prog:
        try:
            # Use faster preset and optimized settings
            (
                ffmpeg.output(
                    bg,
                    final_audio,
                    out_mp4,
                    f="mp4",
                    vcodec="libx264",
                    acodec="aac",
                    preset="faster",
                    video_bitrate="8M",
                    audio_bitrate="192k",
                    pix_fmt="yuv420p",
                    movflags="+faststart",
                    threads=min(multiprocessing.cpu_count(), 8),
                    shortest=None,
                    t=total_len,
                )
                .overwrite_output()
                .global_args("-progress", prog.progress_path, "-nostats", "-loglevel", "error")
                .run(capture_stdout=True, capture_stderr=True)
            )
            logger.info(f"Video rendered successfully: {out_mp4}")
        except ffmpeg.Error as e:
            err = e.stderr.decode("utf8", errors="ignore") if e.stderr else str(e)
            logger.error(f"ffmpeg failed: {err}")
            raise RuntimeError(f"ffmpeg failed:\n{err}")
        finally:
            if pbar.n < 100:
                pbar.update(100 - pbar.n)
            pbar.close()
