"""Parallel TTS generation for improved performance.

This module provides parallel TTS generation capabilities to significantly
speed up audio creation for multiple text segments.
"""
from __future__ import annotations
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

from .tts import tts_to_mp3, tts_to_mp3_with_word_timings, TTSOptions, WordTiming
from .builder import probe_duration
from .logger import get_logger

logger = get_logger(__name__)


def generate_tts_parallel(
    texts: List[str],
    output_paths: List[str],
    tts_opts: TTSOptions,
    max_workers: int = 5,
    capture_word_timings: bool = False
) -> List[Tuple[bool, Optional[List[WordTiming]], Optional[float], Optional[str]]]:
    """Generate TTS audio files in parallel for multiple text segments.
    
    Args:
        texts: List of text strings to convert to speech
        output_paths: List of output file paths (must match texts length)
        tts_opts: TTS options (engine, voice, rate, etc.)
        max_workers: Maximum number of parallel TTS generations (default: 5)
        capture_word_timings: Whether to capture word timing information
    
    Returns:
        List of tuples (success, word_timings, duration, error_msg) for each text.
        - success: True if TTS generation succeeded
        - word_timings: List of WordTiming objects (only if capture_word_timings=True)
        - duration: Audio duration in seconds (None if failed)
        - error_msg: Error message if failed, None otherwise
    
    Example:
        >>> texts = ["Hello world", "Goodbye world"]
        >>> paths = ["hello.mp3", "goodbye.mp3"]
        >>> results = generate_tts_parallel(texts, paths, tts_opts)
        >>> for success, _, duration, error in results:
        ...     if success:
        ...         print(f"Generated {duration:.2f}s audio")
    """
    if len(texts) != len(output_paths):
        raise ValueError("texts and output_paths must have the same length")
    
    if not texts:
        return []
    
    logger.debug(f"Generating TTS for {len(texts)} segments in parallel (max_workers={max_workers})")
    
    def generate_single(text: str, path: str, index: int):
        """Generate TTS for a single text segment."""
        try:
            if capture_word_timings:
                word_timings = tts_to_mp3_with_word_timings(text, path, tts_opts)
            else:
                tts_to_mp3(text, path, tts_opts)
                word_timings = []
            
            duration = probe_duration(path)
            return (index, True, word_timings, duration, None)
        except Exception as e:
            logger.warning(f"Failed to generate TTS for segment {index}: {e}")
            return (index, False, None, None, str(e))
    
    # Use ThreadPoolExecutor for parallel execution
    # edge-tts uses async internally, so threads work well here
    results = [None] * len(texts)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(generate_single, text, path, i): i
            for i, (text, path) in enumerate(zip(texts, output_paths))
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            index, success, word_timings, duration, error = future.result()
            results[index] = (success, word_timings, duration, error)
    
    # Count successes
    success_count = sum(1 for r in results if r[0])
    logger.debug(f"Parallel TTS generation complete: {success_count}/{len(texts)} succeeded")
    
    return results


async def generate_tts_async_batch(
    texts: List[str],
    output_paths: List[str],
    tts_opts: TTSOptions,
    capture_word_timings: bool = False
) -> List[Tuple[bool, Optional[List[WordTiming]], Optional[float], Optional[str]]]:
    """Generate TTS audio files asynchronously for edge-tts.
    
    This is more efficient for edge-tts as it uses true async I/O.
    Falls back to ThreadPoolExecutor approach for pyttsx3.
    
    Args:
        texts: List of text strings to convert to speech
        output_paths: List of output file paths (must match texts length)
        tts_opts: TTS options (engine, voice, rate, etc.)
        capture_word_timings: Whether to capture word timing information
    
    Returns:
        List of tuples (success, word_timings, duration, error_msg) for each text.
    """
    if len(texts) != len(output_paths):
        raise ValueError("texts and output_paths must have the same length")
    
    if not texts:
        return []
    
    # Only use async for edge-tts
    if tts_opts.engine.lower() != "edge_tts":
        # Fall back to thread-based parallel for pyttsx3
        return generate_tts_parallel(texts, output_paths, tts_opts, max_workers=3, 
                                     capture_word_timings=capture_word_timings)
    
    logger.debug(f"Generating TTS for {len(texts)} segments asynchronously")
    
    async def generate_single_async(text: str, path: str, index: int):
        """Generate TTS for a single text segment asynchronously."""
        try:
            if capture_word_timings:
                from .tts import _edge_tts_with_word_timings
                word_timings = await _edge_tts_with_word_timings(text, path, tts_opts)
            else:
                from .tts import _edge_tts_async
                await _edge_tts_async(text, path, tts_opts)
                word_timings = []
            
            duration = probe_duration(path)
            return (index, True, word_timings, duration, None)
        except Exception as e:
            logger.warning(f"Failed to generate TTS for segment {index}: {e}")
            return (index, False, None, None, str(e))
    
    # Create tasks for all text segments
    tasks = [
        generate_single_async(text, path, i)
        for i, (text, path) in enumerate(zip(texts, output_paths))
    ]
    
    # Run all tasks concurrently
    completed = await asyncio.gather(*tasks, return_exceptions=False)
    
    # Sort by index to maintain original order
    results = [None] * len(texts)
    for index, success, word_timings, duration, error in completed:
        results[index] = (success, word_timings, duration, error)
    
    success_count = sum(1 for r in results if r[0])
    logger.debug(f"Async TTS generation complete: {success_count}/{len(texts)} succeeded")
    
    return results
