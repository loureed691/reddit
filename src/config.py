from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
class VideoDurationConfig:
    mode: str = "short"  # "short" or "long"
    target_duration_seconds: int = 90  # 1-2 minutes default
    long_duration_seconds: int = 3600  # 60 minutes

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "VideoDurationConfig":
        mode = str(d.get("mode", "short")).strip().lower()
        if mode not in ("short", "long"):
            raise ValueError(f"Invalid video duration mode: {mode!r}. Expected 'short' or 'long'.")
        return VideoDurationConfig(
            mode=mode,
            target_duration_seconds=_to_int(d.get("target_duration_seconds", 90), 90),
            long_duration_seconds=_to_int(d.get("long_duration_seconds", 3600), 3600),
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
    video_duration: VideoDurationConfig = field(default_factory=VideoDurationConfig)

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
            video_duration=VideoDurationConfig.from_dict(d.get("video_duration", {}) or {}),
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
class AutomationConfig:
    enabled: bool = False
    subreddits: List[str] = field(default_factory=lambda: ["AskReddit"])
    sort_by: str = "hot"  # hot, top, new
    time_filter: str = "day"  # hour, day, week, month, year, all
    min_score: int = 1000
    min_comments: int = 50
    produced_videos_db: str = "produced_videos.json"
    request_timeout: int = 30  # Timeout for Reddit API requests in seconds

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AutomationConfig":
        # Validate subreddits field - ensure it's a list of strings
        raw_subreddits = d.get("subreddits", ["AskReddit"])
        default_subreddits: List[str] = ["AskReddit"]
        
        if isinstance(raw_subreddits, str):
            validated_subreddits: List[str] = [raw_subreddits]
        elif isinstance(raw_subreddits, list):
            # Coerce each element to string, ignoring values that cannot be converted
            validated_subreddits = []
            for item in raw_subreddits:
                try:
                    validated_subreddits.append(str(item))
                except Exception:
                    continue
            if not validated_subreddits:
                validated_subreddits = default_subreddits
        else:
            validated_subreddits = default_subreddits
        
        return AutomationConfig(
            enabled=_to_bool(d.get("enabled", False), False),
            subreddits=validated_subreddits,
            sort_by=str(d.get("sort_by", "hot")),
            time_filter=str(d.get("time_filter", "day")),
            min_score=_to_int(d.get("min_score", 1000), 1000),
            min_comments=_to_int(d.get("min_comments", 50), 50),
            produced_videos_db=str(d.get("produced_videos_db", "produced_videos.json")),
            request_timeout=_to_int(d.get("request_timeout", 30), 30),
        )

@dataclass
class LoggingConfig:
    log_level: str = "INFO"
    console_level: str = "INFO"
    file_level: str = "DEBUG"
    log_dir: str = "logs"
    log_file: str = "reddit_factory.log"
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    enable_file_logging: bool = True
    enable_console_logging: bool = True

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "LoggingConfig":
        return LoggingConfig(
            log_level=str(d.get("log_level", "INFO")).upper(),
            console_level=str(d.get("console_level", "INFO")).upper(),
            file_level=str(d.get("file_level", "DEBUG")).upper(),
            log_dir=str(d.get("log_dir", "logs")),
            log_file=str(d.get("log_file", "reddit_factory.log")),
            max_bytes=_to_int(d.get("max_bytes", 10 * 1024 * 1024), 10 * 1024 * 1024),
            backup_count=_to_int(d.get("backup_count", 5), 5),
            enable_file_logging=_to_bool(d.get("enable_file_logging", True), True),
            enable_console_logging=_to_bool(d.get("enable_console_logging", True), True),
        )

@dataclass
class FactoryConfig:
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FactoryConfig":
        return FactoryConfig(
            settings=SettingsConfig.from_dict(d.get("settings", {}) or {}),
            reddit=RedditConfig.from_dict(d.get("reddit", {}) or {}),
            automation=AutomationConfig.from_dict(d.get("automation", {}) or {}),
            logging=LoggingConfig.from_dict(d.get("logging", {}) or {}),
        )
