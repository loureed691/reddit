"""Text-to-speech module with edge-tts and pyttsx3 support.

Features:
- Primary: edge-tts (high quality, requires internet)
- Fallback: pyttsx3 (offline, robotic)
- Improved error logging and graceful degradation
- Optimized for viral content with faster speech rate and natural voices

Viral Optimization (2026):
- Default voice: en-US-AriaNeural (more conversational and engaging than JennyNeural)
- Default rate: +12% (1.12x speed - optimal for short-form viral content)
- These settings are based on analysis of viral TikTok/YouTube Shorts content
"""
from __future__ import annotations
import asyncio
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional, List, Tuple

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
class WordTiming:
    """Represents timing information for a single word in TTS."""
    text: str
    offset: float  # Start time in seconds
    duration: float  # Duration in seconds

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

async def _edge_tts_with_word_timings(text: str, mp3_path: str, opts: TTSOptions) -> List[WordTiming]:
    """Generate TTS audio and capture word boundary timings.
    
    Returns a list of WordTiming objects containing word text, offset, and duration.
    Falls back to empty list if word boundaries are not available.
    """
    import edge_tts
    _ensure_dir(mp3_path)
    
    communicate = edge_tts.Communicate(text=text, voice=opts.edge_voice, rate=opts.rate, volume=opts.volume)
    
    word_timings: List[WordTiming] = []
    audio_chunks: List[bytes] = []
    
    try:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk.get("data", b""))
            elif chunk["type"] == "WordBoundary":
                # Extract word timing information
                word_text = chunk.get("text", "")
                offset = chunk.get("offset", 0) / 10_000_000.0  # Convert from 100ns units to seconds
                duration = chunk.get("duration", 0) / 10_000_000.0  # Convert from 100ns units to seconds
                
                if word_text and duration > 0:
                    word_timings.append(WordTiming(
                        text=word_text,
                        offset=offset,
                        duration=duration
                    ))
        
        # Write audio data to file
        if audio_chunks:
            with open(mp3_path, "wb") as f:
                f.write(b"".join(audio_chunks))
        
        logger.debug(f"Captured {len(word_timings)} word timings for TTS")
        return word_timings
        
    except Exception as e:
        logger.warning(f"Failed to capture word timings: {e}")
        # Fallback: generate audio without word timings
        await _edge_tts_async(text, mp3_path, opts)
        return []

def tts_to_mp3_with_word_timings(text: str, mp3_path: str, opts: TTSOptions) -> List[WordTiming]:
    """Convert text to MP3 audio file with word timing information.
    
    Returns a list of WordTiming objects. Returns empty list if word timings are not available
    (e.g., when using pyttsx3 or if edge-tts fails to provide word boundaries).
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text for TTS")

    engine = (opts.engine or "edge_tts").strip().lower()
    
    logger.debug(f"Generating TTS with word timings, engine: {engine}, voice: {opts.edge_voice}")

    # Try edge-tts first if selected
    if engine == "edge_tts":
        try:
            return asyncio.run(_edge_tts_with_word_timings(text, mp3_path, opts))
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
            logger.debug(f"TTS generated successfully with pyttsx3 (no word timings available)")
            return []  # pyttsx3 doesn't provide word timings
        except Exception as e:
            logger.error(f"TTS failed (pyttsx3): {e}")
            raise RuntimeError(f"TTS failed (pyttsx3): {e}")

    raise ValueError(f"Unknown TTS engine: {opts.engine}")

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
