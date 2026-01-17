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
    try:
        (
            ffmpeg.output(concat, out_mp3, **{"b:a":"192k"})
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        err = e.stderr.decode("utf8", errors="ignore") if e.stderr else str(e)
        raise RuntimeError(f"ffmpeg failed to concatenate audio files:\n{err}")
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
):
    """Render final video with overlays and audio.
    
    Optimized with better ffmpeg presets and parallel processing.
    Uses filter_complex_script for many images to avoid Windows command line length limits.
    """
    if len(image_paths) != len(image_durations):
        raise ValueError("image_paths and image_durations mismatch")
    
    if not image_paths:
        raise ValueError("No images provided for video rendering")
    
    logger.info(f"Rendering video: {len(image_paths)} images, resolution {W}x{H}")
    logger.debug(f"Output: {out_mp4}")

    # Use filter_complex_script approach when there are many images to avoid
    # Windows command line length limits (32,767 characters)
    USE_FILTER_SCRIPT_THRESHOLD = 50
    use_filter_script = len(image_paths) > USE_FILTER_SCRIPT_THRESHOLD
    
    if use_filter_script:
        logger.debug(f"Using filter_complex_script approach ({len(image_paths)} images)")
        _render_video_with_script(
            background_mp4, out_mp4, audio_mp3, image_paths, image_durations,
            W, H, screenshot_width, opacity, bg_audio_mp3, bg_audio_volume
        )
    else:
        logger.debug(f"Using standard overlay approach ({len(image_paths)} images)")
        _render_video_standard(
            background_mp4, out_mp4, audio_mp3, image_paths, image_durations,
            W, H, screenshot_width, opacity, bg_audio_mp3, bg_audio_volume
        )

def _render_video_standard(
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
):
    """Standard rendering using ffmpeg-python overlay chaining."""
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

    total_len = max(0.1, sum(max(0.0, d) for d in image_durations))
    
    logger.debug(f"Total video length: {total_len:.2f}s")

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
                    preset="faster",  # Faster encoding with moderate quality trade-off
                    video_bitrate="8M",  # Reduced from 20M for faster encoding
                    audio_bitrate="192k",
                    pix_fmt="yuv420p",
                    movflags="+faststart",
                    threads=min(multiprocessing.cpu_count(), 8),  # Limit to 8 cores to avoid system unresponsiveness
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

def _render_video_with_script(
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
):
    """Rendering using filter_complex_script to avoid command line length limits.
    
    This approach writes the complex filter graph to a temporary file and uses
    -filter_complex_script to reference it, avoiding Windows command line length limits.
    """
    import subprocess
    
    total_len = max(0.1, sum(max(0.0, d) for d in image_durations))
    
    # Build the filter complex script
    filter_lines = []
    
    # Background input is [0:v]
    # Audio input will be [1:a] 
    # Images are [2:v], [3:v], etc.
    
    current_stream = "[0:v]"
    t = 0.0
    
    for i, (img_path, dur) in enumerate(zip(image_paths, image_durations)):
        img_idx = i + 2  # Background is 0, audio is 1, images start at 2
        
        # Scale the image
        scaled_label = f"[img{i}scaled]"
        filter_lines.append(f"[{img_idx}:v]scale={screenshot_width}:-1{scaled_label}")
        
        # Apply opacity if not the first image (title)
        if i != 0:
            opaque_label = f"[img{i}opaque]"
            filter_lines.append(f"{scaled_label}colorchannelmixer=aa={opacity}{opaque_label}")
            overlay_input = opaque_label
        else:
            overlay_input = scaled_label
        
        # Overlay on the current stream
        overlay_output = f"[overlay{i}]"
        start_time = t
        end_time = t + dur
        filter_lines.append(
            f"{current_stream}{overlay_input}overlay="
            f"x=(main_w-overlay_w)/2:y=(main_h-overlay_h)/2:"
            f"enable='between(t,{start_time},{end_time})'{overlay_output}"
        )
        
        current_stream = overlay_output
        t += dur
    
    # Final scale
    filter_lines.append(f"{current_stream}scale={W}:{H}[vout]")
    
    # Audio handling
    if bg_audio_mp3 and exists(bg_audio_mp3) and bg_audio_volume > 0:
        # Background audio will be the last input
        bg_audio_idx = len(image_paths) + 2
        filter_lines.append(f"[{bg_audio_idx}:a]volume={bg_audio_volume}[bg_audio]")
        filter_lines.append(f"[1:a][bg_audio]amix=duration=longest[aout]")
    else:
        filter_lines.append(f"[1:a]anull[aout]")
    
    # Write filter script to temporary file
    filter_script = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    filter_script_path = filter_script.name
    filter_script.write(";\n".join(filter_lines))
    filter_script.close()
    
    logger.debug(f"Filter script written to: {filter_script_path}")
    logger.debug(f"Filter script size: {os.path.getsize(filter_script_path)} bytes")
    
    pbar = tqdm(total=100, desc="Encoding", unit="%", ncols=80)
    def on_update(p: float):
        target = max(0.0, min(100.0, p*100))
        delta = target - pbar.n
        if delta > 0:
            pbar.update(delta)
    
    with ProgressFfmpeg(total_len, on_update) as prog:
        try:
            # Build ffmpeg command manually
            cmd = ["ffmpeg"]
            
            # Add inputs
            cmd.extend(["-i", background_mp4])
            cmd.extend(["-i", audio_mp3])
            for img_path in image_paths:
                cmd.extend(["-i", img_path])
            
            # Add background audio if present
            if bg_audio_mp3 and exists(bg_audio_mp3) and bg_audio_volume > 0:
                cmd.extend(["-i", bg_audio_mp3])
            
            # Add filter script
            cmd.extend(["-filter_complex_script", filter_script_path])
            
            # Map outputs
            cmd.extend(["-map", "[vout]", "-map", "[aout]"])
            
            # Output settings
            cmd.extend([
                "-f", "mp4",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "faster",
                "-b:v", "8M",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-threads", str(min(multiprocessing.cpu_count(), 8)),
                "-t", str(total_len),
                "-y",  # Overwrite output
                "-progress", prog.progress_path,
                "-nostats",
                "-loglevel", "error",
                out_mp4
            ])
            
            logger.debug(f"Running ffmpeg with {len(cmd)} arguments")
            
            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False
            )
            
            if result.returncode != 0:
                err = result.stderr.decode("utf8", errors="ignore") if result.stderr else "Unknown error"
                logger.error(f"ffmpeg failed: {err}")
                raise RuntimeError(f"ffmpeg failed:\n{err}")
            
            logger.info(f"Video rendered successfully: {out_mp4}")
        finally:
            # Clean up filter script
            try:
                os.remove(filter_script_path)
            except Exception:
                pass
            
            if pbar.n < 100:
                pbar.update(100 - pbar.n)
            pbar.close()
