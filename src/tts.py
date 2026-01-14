from __future__ import annotations
import asyncio
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

import ffmpeg

@dataclass
class TTSOptions:
    engine: str = "edge_tts"  # edge_tts | pyttsx3
    edge_voice: str = "en-US-JennyNeural"
    rate: str = "+0%"
    volume: str = "+0%"

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

def tts_to_mp3(text: str, mp3_path: str, opts: TTSOptions) -> None:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text for TTS")

    engine = (opts.engine or "edge_tts").strip().lower()

    # Try edge-tts first if selected
    if engine == "edge_tts":
        try:
            asyncio.run(_edge_tts_async(text, mp3_path, opts))
            return
        except Exception:
            # fallback to pyttsx3
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
            return
        except Exception as e:
            raise RuntimeError(f"TTS failed (pyttsx3): {e}")

    raise ValueError(f"Unknown TTS engine: {opts.engine}")
