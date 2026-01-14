from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

def _get(d: Dict[str, Any], path, default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def _to_bool(v, default=False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("1","true","yes","y","on"):
        return True
    if s in ("0","false","no","n","off",""):
        return False
    return default

def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except Exception:
        return default

def _to_float(v, default=0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default

@dataclass
class VoiceConfig:
    engine: str = "edge_tts"     # edge_tts | pyttsx3
    edge_voice: str = "en-US-JennyNeural"
    rate: str = "+0%"
    volume: str = "+0%"

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "VoiceConfig":
        return VoiceConfig(
            engine=str(d.get("engine","edge_tts")),
            edge_voice=str(d.get("edge_voice","en-US-JennyNeural")),
            rate=str(d.get("rate","+0%")),
            volume=str(d.get("volume","+0%")),
        )

@dataclass
class BackgroundConfig:
    enable_extra_audio: bool = True
    background_audio_volume: float = 0.12
    auto_generate_background: bool = True
    background_seconds: int = 0
    background_path: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "BackgroundConfig":
        return BackgroundConfig(
            enable_extra_audio=_to_bool(d.get("enable_extra_audio", True), True),
            background_audio_volume=_to_float(d.get("background_audio_volume", 0.12), 0.12),
            auto_generate_background=_to_bool(d.get("auto_generate_background", True), True),
            background_seconds=_to_int(d.get("background_seconds", 0), 0),
            background_path=d.get("background_path", None),
        )

@dataclass
class SettingsConfig:
    resolution_w: int = 1080
    resolution_h: int = 1920
    opacity: float = 0.92
    max_comments: int = 12
    language: str = "en"
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SettingsConfig":
        return SettingsConfig(
            resolution_w=_to_int(d.get("resolution_w", 1080), 1080),
            resolution_h=_to_int(d.get("resolution_h", 1920), 1920),
            opacity=_to_float(d.get("opacity", 0.92), 0.92),
            max_comments=_to_int(d.get("max_comments", 12), 12),
            language=str(d.get("language","en")),
            voice=VoiceConfig.from_dict(d.get("voice", {}) or {}),
            background=BackgroundConfig.from_dict(d.get("background", {}) or {}),
        )

@dataclass
class RedditConfig:
    user_agent: str = "reddit-video-factory/1.0"
    prefer_top_comments: bool = True

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RedditConfig":
        return RedditConfig(
            user_agent=str(d.get("user_agent","reddit-video-factory/1.0")),
            prefer_top_comments=_to_bool(d.get("prefer_top_comments", True), True),
        )

@dataclass
class FactoryConfig:
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FactoryConfig":
        return FactoryConfig(
            settings=SettingsConfig.from_dict(d.get("settings", {}) or {}),
            reddit=RedditConfig.from_dict(d.get("reddit", {}) or {}),
        )
