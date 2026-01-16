"""Performance monitoring and optimization utilities.

This module provides performance monitoring, profiling, and optimization
utilities for the video creation pipeline.
"""
from __future__ import annotations
import subprocess
import time
from contextlib import contextmanager
from typing import Dict, Optional, List
from dataclasses import dataclass

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    fetch_time: float = 0.0
    tts_time: float = 0.0
    render_cards_time: float = 0.0
    background_time: float = 0.0
    assembly_time: float = 0.0
    total_time: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for logging."""
        return {
            "fetch_time": self.fetch_time,
            "tts_time": self.tts_time,
            "render_cards_time": self.render_cards_time,
            "background_time": self.background_time,
            "assembly_time": self.assembly_time,
            "total_time": self.total_time,
        }
    
    def log_summary(self) -> None:
        """Log a summary of the metrics."""
        logger.info("=" * 60)
        logger.info("Performance Summary:")
        logger.info(f"  Fetch Reddit data:  {self.fetch_time:7.2f}s")
        logger.info(f"  Generate TTS:       {self.tts_time:7.2f}s")
        logger.info(f"  Render cards:       {self.render_cards_time:7.2f}s")
        logger.info(f"  Background video:   {self.background_time:7.2f}s")
        logger.info(f"  Assemble video:     {self.assembly_time:7.2f}s")
        logger.info(f"  ─────────────────────────────")
        logger.info(f"  Total time:         {self.total_time:7.2f}s")
        logger.info("=" * 60)


@contextmanager
def timer(name: str):
    """Context manager for timing operations.
    
    Example:
        >>> with timer("TTS generation"):
        ...     generate_tts()
    """
    start = time.time()
    logger.debug(f"Starting: {name}")
    try:
        yield
    finally:
        elapsed = time.time() - start
        logger.debug(f"Completed: {name} ({elapsed:.2f}s)")


def detect_gpu_encoder() -> Optional[str]:
    """Detect available GPU encoder for hardware acceleration.
    
    Returns:
        Name of the encoder to use (e.g., 'h264_nvenc', 'h264_qsv', 'h264_videotoolbox')
        or None if no GPU encoder is available.
    """
    # Try to detect encoders via ffmpeg
    encoders_to_try = [
        ('h264_nvenc', 'NVIDIA GPU (NVENC)'),
        ('h264_qsv', 'Intel Quick Sync Video'),
        ('h264_videotoolbox', 'Apple VideoToolbox'),
        ('h264_amf', 'AMD GPU'),
    ]
    
    for encoder, description in encoders_to_try:
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if encoder in result.stdout:
                logger.info(f"GPU encoder detected: {encoder} ({description})")
                return encoder
        except Exception:
            continue
    
    logger.debug("No GPU encoder detected, using software encoding (libx264)")
    return None


def get_optimal_encoder_settings(encoder: Optional[str] = None) -> Dict[str, str]:
    """Get optimal encoder settings based on available hardware.
    
    Args:
        encoder: Encoder name (e.g., 'h264_nvenc'), or None to auto-detect
    
    Returns:
        Dictionary of ffmpeg encoder settings
    """
    if encoder is None:
        encoder = detect_gpu_encoder()
    
    if encoder == 'h264_nvenc':
        # NVIDIA GPU encoding settings
        return {
            'vcodec': 'h264_nvenc',
            'preset': 'p4',  # Fast preset for NVENC
            'video_bitrate': '8M',
        }
    elif encoder == 'h264_qsv':
        # Intel Quick Sync settings
        return {
            'vcodec': 'h264_qsv',
            'preset': 'faster',
            'video_bitrate': '8M',
        }
    elif encoder == 'h264_videotoolbox':
        # Apple VideoToolbox settings
        return {
            'vcodec': 'h264_videotoolbox',
            'video_bitrate': '8M',
        }
    elif encoder == 'h264_amf':
        # AMD GPU settings
        return {
            'vcodec': 'h264_amf',
            'quality': 'balanced',
            'video_bitrate': '8M',
        }
    else:
        # Software encoding (libx264) - already optimized
        return {
            'vcodec': 'libx264',
            'preset': 'faster',
            'video_bitrate': '8M',
        }


class PerformanceProfiler:
    """Simple profiler for tracking pipeline performance."""
    
    def __init__(self):
        self.metrics = PerformanceMetrics()
        self._start_time = None
        self._current_phase = None
        self._phase_start = None
    
    def start(self) -> None:
        """Start the profiler."""
        self._start_time = time.time()
        logger.debug("Performance profiling started")
    
    def start_phase(self, phase: str) -> None:
        """Start timing a phase."""
        if self._current_phase:
            self.end_phase()
        self._current_phase = phase
        self._phase_start = time.time()
        logger.debug(f"Phase started: {phase}")
    
    def end_phase(self) -> None:
        """End the current phase."""
        if not self._current_phase or not self._phase_start:
            return
        
        elapsed = time.time() - self._phase_start
        
        # Update metrics
        if self._current_phase == "fetch":
            self.metrics.fetch_time = elapsed
        elif self._current_phase == "tts":
            self.metrics.tts_time = elapsed
        elif self._current_phase == "render":
            self.metrics.render_cards_time = elapsed
        elif self._current_phase == "background":
            self.metrics.background_time = elapsed
        elif self._current_phase == "assembly":
            self.metrics.assembly_time = elapsed
        
        logger.debug(f"Phase completed: {self._current_phase} ({elapsed:.2f}s)")
        self._current_phase = None
        self._phase_start = None
    
    def finish(self) -> PerformanceMetrics:
        """Finish profiling and return metrics."""
        if self._current_phase:
            self.end_phase()
        
        if self._start_time:
            self.metrics.total_time = time.time() - self._start_time
        
        self.metrics.log_summary()
        return self.metrics
