"""Word-by-word caption rendering module for viral video effects.

This module generates word-by-word animated captions that sync with TTS audio,
a popular effect on TikTok, YouTube Shorts, and Instagram Reels.

Features:
- Word-by-word text appearance synchronized with spoken audio
- Customizable styling (font, colors, borders, shadows)
- Optimized for viral short-form content
"""
from __future__ import annotations
import json
import os
from typing import List, Optional

from .tts import WordTimestamp
from .logger import get_logger

logger = get_logger(__name__)


def generate_word_captions_filter(
    word_timestamps: List[WordTimestamp],
    video_width: int = 1080,
    video_height: int = 1920,
    font_size: int = 60,
    font_color: str = "white",
    border_color: str = "black",
    border_width: int = 3,
    y_position: Optional[int] = None,
) -> str:
    """Generate ffmpeg drawtext filter chain for word-by-word captions.
    
    Args:
        word_timestamps: List of word timestamps from TTS
        video_width: Video width in pixels
        video_height: Video height in pixels
        font_size: Font size for captions
        font_color: Text color (ffmpeg color name or hex)
        border_color: Border/outline color
        border_width: Border width in pixels
        y_position: Y position (None = bottom third of screen)
        
    Returns:
        FFmpeg drawtext filter string for all words
    """
    if not word_timestamps:
        logger.warning("No word timestamps provided, skipping captions")
        return ""
    
    # Default position: bottom third of screen
    if y_position is None:
        y_position = int(video_height * 0.7)
    
    # Build drawtext filter for each word
    filters = []
    for i, word_ts in enumerate(word_timestamps):
        # Convert milliseconds to seconds
        start_sec = word_ts.start_ms / 1000.0
        end_sec = word_ts.end_ms / 1000.0
        
        # Escape special characters in text for ffmpeg
        escaped_word = _escape_ffmpeg_text(word_ts.word)
        
        # Create drawtext filter for this word
        # Using enable parameter to show word only during its time window
        filter_str = (
            f"drawtext="
            f"text='{escaped_word}':"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}:"
            f"borderw={border_width}:"
            f"bordercolor={border_color}:"
            f"x=(w-text_w)/2:"  # Center horizontally
            f"y={y_position}:"
            f"enable='between(t,{start_sec:.3f},{end_sec:.3f})'"
        )
        filters.append(filter_str)
    
    logger.debug(f"Generated {len(filters)} word caption filters")
    return ",".join(filters)


def _escape_ffmpeg_text(text: str) -> str:
    r"""Escape special characters for ffmpeg drawtext filter.
    
    FFmpeg drawtext requires escaping: ' \ : [ ]
    """
    text = text.replace("\\", "\\\\")  # Backslash must be first
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    return text


def save_word_timestamps_json(
    word_timestamps: List[WordTimestamp], output_path: str
) -> None:
    """Save word timestamps to JSON file for debugging/inspection.
    
    Args:
        word_timestamps: List of word timestamps
        output_path: Path to save JSON file
    """
    data = [
        {
            "word": wt.word,
            "start_ms": wt.start_ms,
            "end_ms": wt.end_ms,
            "duration_ms": wt.end_ms - wt.start_ms,
        }
        for wt in word_timestamps
    ]
    
    # Create directory only if path has a directory component
    dir_path = os.path.dirname(output_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.debug(f"Saved {len(data)} word timestamps to {output_path}")
