"""Text-to-speech module with edge-tts and pyttsx3 support.

Features:
- Primary: edge-tts (high quality, requires internet)
- Fallback: pyttsx3 (offline, robotic)
- Improved error logging and graceful degradation
- Optimized for viral content with faster speech rate and natural voices
- Word-level timestamp extraction for word-by-word subtitle sync

Viral Optimization (2026):
- Default voice: en-US-AriaNeural (more conversational and engaging than JennyNeural)
- Default rate: +12% (1.12x speed - optimal for short-form viral content)
- These settings are based on analysis of viral TikTok/YouTube Shorts content
"""
from __future__ import annotations
import asyncio
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

import ffmpeg

from .logger import get_logger

logger = get_logger(__name__)

@dataclass
class TTSOptions:
    engine: str = "edge_tts"  # edge_tts | pyttsx3
    edge_voice: str = "en-US-AriaNeural"  # Optimized for viral content
    rate: str = "+12%"  # Slightly faster for better engagement (viral optimization)
    volume: str = "+0%"

@dataclass
class WordTimestamp:
    """Represents a word with its timing information."""
    word: str
    start_ms: float  # Start time in milliseconds
    end_ms: float    # End time in milliseconds

def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

def _ffmpeg_wav_to_mp3(wav_path: str, mp3_path: str) -> None:
    _ensure_dir(mp3_path)
    (
        ffmpeg
        .input(wav_path)
        .output(mp3_path, acodec="libmp3lame", **{"b:a": "192k"})
        .overwrite_output()
        .run(quiet=True)
    )

async def _edge_tts_async(text: str, mp3_path: str, opts: TTSOptions) -> None:
    import edge_tts
    _ensure_dir(mp3_path)
    communicate = edge_tts.Communicate(text=text, voice=opts.edge_voice, rate=opts.rate, volume=opts.volume)
    await communicate.save(mp3_path)

async def _edge_tts_with_timestamps_async(
    text: str, mp3_path: str, opts: TTSOptions
) -> List[WordTimestamp]:
    """Generate TTS audio and extract word-level timestamps.
    
    Returns:
        List of WordTimestamp objects with timing information for each word.
    """
    import edge_tts
    _ensure_dir(mp3_path)
    
    communicate = edge_tts.Communicate(text=text, voice=opts.edge_voice, rate=opts.rate, volume=opts.volume)
    submaker = edge_tts.SubMaker()
    
    with open(mp3_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)
    
    # Extract word timestamps from submaker
    word_timestamps = []
    for subtitle in submaker.cues:
        word_timestamps.append(
            WordTimestamp(
                word=subtitle.content,
                start_ms=subtitle.start.total_seconds() * 1000,
                end_ms=subtitle.end.total_seconds() * 1000,
            )
        )
    
    logger.debug(f"Generated {len(word_timestamps)} word timestamps")
    return word_timestamps

def tts_to_mp3(text: str, mp3_path: str, opts: TTSOptions) -> None:
    """Convert text to MP3 audio file using configured TTS engine.
    
    Tries edge-tts first for quality, falls back to pyttsx3 if unavailable.
    Includes improved error handling and logging.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text for TTS")

    engine = (opts.engine or "edge_tts").strip().lower()
    
    logger.debug(f"Generating TTS with engine: {engine}, voice: {opts.edge_voice}")

    # Try edge-tts first if selected
    if engine == "edge_tts":
        try:
            asyncio.run(_edge_tts_async(text, mp3_path, opts))
            logger.debug(f"TTS generated successfully: {mp3_path}")
            return
        except Exception as e:
            # Log the error and fallback to pyttsx3
            logger.warning(f"edge-tts failed ({e}), falling back to pyttsx3")
            engine = "pyttsx3"

    if engine == "pyttsx3":
        try:
            import pyttsx3
            _ensure_dir(mp3_path)
            # pyttsx3 outputs WAV easier, then convert to mp3
            tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
            engine_obj = pyttsx3.init()
            engine_obj.setProperty("rate", 170)
            engine_obj.save_to_file(text, tmp_wav)
            engine_obj.runAndWait()
            _ffmpeg_wav_to_mp3(tmp_wav, mp3_path)
            try:
                os.remove(tmp_wav)
            except Exception:
                pass
            logger.debug(f"TTS generated successfully with pyttsx3: {mp3_path}")
            return
        except Exception as e:
            logger.error(f"TTS failed (pyttsx3): {e}")
            raise RuntimeError(f"TTS failed (pyttsx3): {e}")

    raise ValueError(f"Unknown TTS engine: {opts.engine}")

def tts_to_mp3_with_timestamps(
    text: str, mp3_path: str, opts: TTSOptions
) -> List[WordTimestamp]:
    """Convert text to MP3 and extract word-level timestamps.
    
    Only works with edge-tts engine. Falls back to basic TTS without timestamps
    for pyttsx3 or if edge-tts fails.
    
    Returns:
        List of WordTimestamp objects. Empty list if timestamps unavailable.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text for TTS")

    engine = (opts.engine or "edge_tts").strip().lower()
    
    logger.debug(f"Generating TTS with timestamps, engine: {engine}, voice: {opts.edge_voice}")

    # Try edge-tts with timestamps
    if engine == "edge_tts":
        try:
            timestamps = asyncio.run(_edge_tts_with_timestamps_async(text, mp3_path, opts))
            logger.debug(f"TTS with timestamps generated successfully: {mp3_path}")
            return timestamps
        except Exception as e:
            # Log the error and fallback to pyttsx3
            logger.warning(f"edge-tts failed ({e}), falling back to pyttsx3 (no timestamps)")
            engine = "pyttsx3"

    # Fallback to pyttsx3 without timestamps
    if engine == "pyttsx3":
        try:
            import pyttsx3
            _ensure_dir(mp3_path)
            tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
            engine_obj = pyttsx3.init()
            engine_obj.setProperty("rate", 170)
            engine_obj.save_to_file(text, tmp_wav)
            engine_obj.runAndWait()
            _ffmpeg_wav_to_mp3(tmp_wav, mp3_path)
            try:
                os.remove(tmp_wav)
            except Exception:
                pass
            logger.debug(f"TTS generated successfully with pyttsx3 (no timestamps): {mp3_path}")
            return []  # No timestamps available
        except Exception as e:
            logger.error(f"TTS failed (pyttsx3): {e}")
            raise RuntimeError(f"TTS failed (pyttsx3): {e}")

    return []
