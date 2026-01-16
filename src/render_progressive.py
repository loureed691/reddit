"""Progressive text rendering for word-by-word animation.

This module provides functionality to render cards with text appearing word by word,
synchronized with TTS audio for enhanced viewer engagement.
"""
from __future__ import annotations
import os
import re
from typing import List, Tuple

from .render_cards import render_title_card, render_comment_card
from .tts import WordTiming
from .logger import get_logger

logger = get_logger(__name__)

# Maximum number of TTS fragments that can form a single original word
# Most contractions split into 2-3 parts (e.g., "What's" -> "What" + "s")
MAX_CONTRACTION_PARTS = 5


def create_progressive_text(
    word_timings: List[WordTiming],
    original_text: str = ""
) -> List[Tuple[str, float, float]]:
    """Create progressive text reveals from word timings, aligned with original text.
    
    Args:
        word_timings: List of WordTiming objects from TTS
        original_text: The original text (with proper formatting/punctuation)
    
    Returns:
        List of tuples (partial_text, start_time, duration) where:
        - partial_text: Text to display up to this point (from original text)
        - start_time: When to show this frame (seconds from start)
        - duration: How long to show this frame (seconds)
    """
    if not word_timings:
        # Return empty list to signal no progressive frames
        return []
    
    progressive_frames: List[Tuple[str, float, float]] = []
    
    # If no original text provided, fall back to using TTS text directly
    if not original_text:
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
    
    # Align TTS word timings with original text
    # Split original text into words (preserving word boundaries)
    # Split on whitespace but keep track of positions
    original_words = re.findall(r'\S+', original_text)
    
    # Normalize words for matching (lowercase, remove punctuation)
    # Note: \w already includes digits, letters, and underscores
    def normalize_word(word: str) -> str:
        return re.sub(r'[^\w]', '', word.lower())
    
    # Build mapping from TTS words to original text positions
    tts_idx = 0
    original_idx = 0
    word_map = []  # List of (original_word, tts_timing_idx)
    
    while tts_idx < len(word_timings) and original_idx < len(original_words):
        tts_word_normalized = normalize_word(word_timings[tts_idx].text)
        orig_word_normalized = normalize_word(original_words[original_idx])
        
        if tts_word_normalized == orig_word_normalized:
            # Direct match
            word_map.append((original_words[original_idx], tts_idx))
            tts_idx += 1
            original_idx += 1
        elif (len(tts_word_normalized) > 0 and 
              orig_word_normalized.startswith(tts_word_normalized) and
              len(tts_word_normalized) < len(orig_word_normalized)):
            # TTS word is a prefix of original word (e.g., contraction split: "What" + "s" = "Whats")
            # Only trigger this if TTS word is shorter, to avoid false matches like "he" in "the"
            # Accumulate TTS words until we match the original word
            accumulated_tts = tts_word_normalized
            start_tts_idx = tts_idx
            tts_idx += 1
            
            # Safety: limit iterations to prevent infinite loop
            iterations = 0
            
            while (tts_idx < len(word_timings) and 
                   accumulated_tts != orig_word_normalized and
                   iterations < MAX_CONTRACTION_PARTS):
                next_tts = normalize_word(word_timings[tts_idx].text)
                accumulated_tts += next_tts
                tts_idx += 1
                iterations += 1
                
                # If we've accumulated more than the original word, we've gone too far
                if len(accumulated_tts) > len(orig_word_normalized):
                    logger.debug(f"Contraction accumulation exceeded original word length, stopping")
                    break
            
            # Use the first TTS timing for this original word
            word_map.append((original_words[original_idx], start_tts_idx))
            original_idx += 1
        else:
            # Mismatch - skip TTS word (might be TTS artifact)
            logger.debug(f"Skipping unmatched TTS word: '{word_timings[tts_idx].text}'")
            tts_idx += 1
    
    # Add any remaining original words with the last known timing
    if word_timings and original_idx < len(original_words):
        last_tts_idx = len(word_timings) - 1
        while original_idx < len(original_words):
            word_map.append((original_words[original_idx], last_tts_idx))
            original_idx += 1
    
    # If no word map was built, fall back to empty result
    if not word_map:
        logger.warning("Could not map TTS timings to original text, returning empty frames")
        return []
    
    # Build progressive frames using original text
    accumulated_text = ""
    for i, (orig_word, tts_idx) in enumerate(word_map):
        # Add word to accumulated text with proper spacing
        if accumulated_text:
            accumulated_text += " " + orig_word
        else:
            accumulated_text = orig_word
        
        # Get timing from TTS - safe access with bounds check
        if tts_idx < len(word_timings):
            timing = word_timings[tts_idx]
        elif word_timings:
            timing = word_timings[-1]
        else:
            # No timings available, skip
            logger.warning("No word timings available during frame building")
            break
        
        # Calculate duration: until next word or end of audio
        if i < len(word_map) - 1:
            next_tts_idx = word_map[i + 1][1]
            if next_tts_idx < len(word_timings):
                duration = word_timings[next_tts_idx].offset - timing.offset
            else:
                duration = timing.duration
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
    progressive_frames = create_progressive_text(word_timings, title)
    
    if not progressive_frames:
        # No word timings: render single card with full audio duration
        img = render_title_card(title, subtitle)
        path = os.path.join(png_dir, f"{base_name}.png")
        img.save(path, optimize=False)
        return [(path, audio_duration)]
    
    result: List[Tuple[str, float]] = []
    
    for i, (partial_text, _start_time, duration) in enumerate(progressive_frames):
        img = render_title_card(partial_text, subtitle)
        path = os.path.join(png_dir, f"{base_name}_{i:03d}.png")
        img.save(path, optimize=False)
        result.append((path, duration))
        
    logger.debug(f"Rendered {len(result)} progressive title cards")
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
    progressive_frames = create_progressive_text(word_timings, body)
    
    if not progressive_frames:
        # No word timings: render single card with full audio duration
        img = render_comment_card(author, body, score)
        path = os.path.join(png_dir, f"{base_name}.png")
        img.save(path, optimize=False)
        return [(path, audio_duration)]
    
    result: List[Tuple[str, float]] = []
    
    for i, (partial_text, _start_time, duration) in enumerate(progressive_frames):
        img = render_comment_card(author, partial_text, score)
        path = os.path.join(png_dir, f"{base_name}_{i:03d}.png")
        img.save(path, optimize=False)
        result.append((path, duration))
        
    logger.debug(f"Rendered {len(result)} progressive comment cards for {base_name}")
    return result
