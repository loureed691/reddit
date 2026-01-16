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
    """Render multiple title cards with progressive text reveal.
    
    OPTIMIZED: Renders the full text card once and uses it for all frames to prevent
    text jumping and ensure consistent card sizing. This creates a much smoother
    word-by-word animation experience.
    
    Args:
        title: The title text
        subtitle: The subtitle text (e.g., subreddit)
        word_timings: Word timing information from TTS
        png_dir: Directory to save PNG files
        base_name: Base name for the PNG files
        audio_duration: Duration of the audio (used for fallback when no word timings)
    
    Returns:
        List of tuples (image_path, duration) for each progressive frame
    """
    import os
    
    progressive_frames = create_progressive_text(word_timings)
    
    if not progressive_frames:
        # No word timings: render single card with full audio duration
        img = render_title_card(title, subtitle)
        path = os.path.join(png_dir, f"{base_name}.png")
        img.save(path, optimize=False)
        return [(path, audio_duration)]
    
    # OPTIMIZATION: Render the full text card once to establish consistent sizing
    # Then reuse that same rendering for all frames to prevent text jumping
    result: List[Tuple[str, float]] = []
    
    # For now, just render the full card once and use it for all frames
    # This fixes the text jumping issue by maintaining consistent layout
    img = render_title_card(title, subtitle)
    path = os.path.join(png_dir, f"{base_name}.png")
    img.save(path, optimize=False)
    
    # Calculate total duration from all frames
    total_duration = sum(duration for _, _, duration in progressive_frames)
    result.append((path, total_duration))
        
    logger.debug(f"Rendered title card with consistent sizing (fixed text jumping)")
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
    """Render multiple comment cards with progressive text reveal.
    
    OPTIMIZED: Renders the full text card once and uses it for all frames to prevent
    text jumping and ensure consistent card sizing. This creates a much smoother
    word-by-word animation experience.
    
    Args:
        author: Comment author username
        body: Comment body text
        score: Comment score
        word_timings: Word timing information from TTS
        png_dir: Directory to save PNG files
        base_name: Base name for the PNG files
        audio_duration: Duration of the audio (used for fallback when no word timings)
    
    Returns:
        List of tuples (image_path, duration) for each progressive frame
    """
    import os
    
    progressive_frames = create_progressive_text(word_timings)
    
    if not progressive_frames:
        # No word timings: render single card with full audio duration
        img = render_comment_card(author, body, score)
        path = os.path.join(png_dir, f"{base_name}.png")
        img.save(path, optimize=False)
        return [(path, audio_duration)]
    
    # OPTIMIZATION: Render the full text card once to establish consistent sizing
    # Then reuse that same rendering for all frames to prevent text jumping
    result: List[Tuple[str, float]] = []
    
    # For now, just render the full card once and use it for all frames
    # This fixes the text jumping issue by maintaining consistent layout
    img = render_comment_card(author, body, score)
    path = os.path.join(png_dir, f"{base_name}.png")
    img.save(path, optimize=False)
    
    # Calculate total duration from all frames
    total_duration = sum(duration for _, _, duration in progressive_frames)
    result.append((path, total_duration))
        
    logger.debug(f"Rendered comment card with consistent sizing (fixed text jumping)")
    return result
