"""Progressive text rendering for word-by-word animation.

This module provides functionality to render cards with text appearing word by word,
synchronized with TTS audio for enhanced viewer engagement.
"""
from __future__ import annotations
from typing import List, Tuple

from .render_cards import render_title_card, render_comment_card
from .tts import WordTiming
from .logger import get_logger

logger = get_logger(__name__)


def _calculate_duration_from_timings(word_timings: List[WordTiming], fallback_duration: float) -> float:
    """Calculate total duration from word timings or use fallback.
    
    Args:
        word_timings: List of WordTiming objects from TTS
        fallback_duration: Duration to use if word timings are not available
    
    Returns:
        Total duration in seconds
    """
    if not word_timings:
        return fallback_duration
    
    progressive_frames = create_progressive_text(word_timings)
    if not progressive_frames:
        return fallback_duration
    
    total_duration = sum(duration for _, _, duration in progressive_frames)
    return total_duration if total_duration > 0 else fallback_duration


def create_progressive_text(word_timings: List[WordTiming]) -> List[Tuple[str, float, float]]:
    """Create progressive text reveals from word timings.
    
    Args:
        word_timings: List of WordTiming objects from TTS
    
    Returns:
        List of tuples (partial_text, start_time, duration) where:
        - partial_text: Text to display up to this point
        - start_time: When to show this frame (seconds from start)
        - duration: How long to show this frame (seconds)
    """
    if not word_timings:
        # Return empty list to signal no progressive frames
        return []
    
    progressive_frames: List[Tuple[str, float, float]] = []
    
    # Build progressive text using word timings directly
    # This ensures we match the TTS output exactly
    accumulated_text = ""
    
    for i, timing in enumerate(word_timings):
        # Add word to accumulated text with proper spacing
        if accumulated_text:
            accumulated_text += " " + timing.text
        else:
            accumulated_text = timing.text
        
        # Calculate duration: until next word or end of audio
        if i < len(word_timings) - 1:
            duration = word_timings[i+1].offset - timing.offset
        else:
            # Last word: use its duration
            duration = timing.duration
        
        progressive_frames.append((accumulated_text, timing.offset, duration))
    
    return progressive_frames


def render_progressive_title_cards(
    title: str,
    subtitle: str,
    word_timings: List[WordTiming],
    png_dir: str,
    base_name: str = "title",
    audio_duration: float = 0.0
) -> List[Tuple[str, float]]:
    """Render title cards with optional progressive text reveal.
    
    NOTE: Progressive word-by-word animation has been simplified to show full text
    to prevent the "text jumping" issue caused by changing text wrapping between frames.
    The original implementation rendered partial text for each word, causing the layout
    to shift as more words were added. This created a poor user experience.
    
    The current implementation renders a single card with full text, which provides
    a consistent, stable layout. Future enhancements could implement proper word-by-word
    animation using masking or highlighting techniques while maintaining layout stability.
    
    Args:
        title: The title text
        subtitle: The subtitle text (e.g., subreddit)
        word_timings: Word timing information from TTS (currently not used)
        png_dir: Directory to save PNG files
        base_name: Base name for the PNG files
        audio_duration: Duration of the audio (used for fallback when no word timings)
    
    Returns:
        List of tuples (image_path, duration) for each frame (currently always single frame)
    """
    import os
    
    # Render single card with full text to avoid text jumping issues
    img = render_title_card(title, subtitle)
    path = os.path.join(png_dir, f"{base_name}.png")
    img.save(path, optimize=False)
    
    # Calculate duration from word timings if available, otherwise use fallback
    final_duration = _calculate_duration_from_timings(word_timings, audio_duration)
    
    result = [(path, final_duration)]
    logger.debug(f"Rendered title card with full text (word-by-word disabled to prevent jumping)")
    return result


def render_progressive_comment_cards(
    author: str,
    body: str,
    score: int,
    word_timings: List[WordTiming],
    png_dir: str,
    base_name: str = "comment_0",
    audio_duration: float = 0.0
) -> List[Tuple[str, float]]:
    """Render comment cards with optional progressive text reveal.
    
    NOTE: Progressive word-by-word animation has been simplified to show full text
    to prevent the "text jumping" issue caused by changing text wrapping between frames.
    The original implementation rendered partial text for each word, causing the layout
    to shift as more words were added. This created a poor user experience.
    
    The current implementation renders a single card with full text, which provides
    a consistent, stable layout. Future enhancements could implement proper word-by-word
    animation using masking or highlighting techniques while maintaining layout stability.
    
    Args:
        author: Comment author username
        body: Comment body text
        score: Comment score
        word_timings: Word timing information from TTS (currently not used)
        png_dir: Directory to save PNG files
        base_name: Base name for the PNG files
        audio_duration: Duration of the audio (used for fallback when no word timings)
    
    Returns:
        List of tuples (image_path, duration) for each frame (currently always single frame)
    """
    import os
    
    # Render single card with full text to avoid text jumping issues
    img = render_comment_card(author, body, score)
    path = os.path.join(png_dir, f"{base_name}.png")
    img.save(path, optimize=False)
    
    # Calculate duration from word timings if available, otherwise use fallback
    final_duration = _calculate_duration_from_timings(word_timings, audio_duration)
    
    result = [(path, final_duration)]
    logger.debug(f"Rendered comment card with full text (word-by-word disabled to prevent jumping)")
    return result
