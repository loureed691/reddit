"""Caching utilities for video generation optimization.

This module provides caching functionality for expensive operations:
- Background video caching (duration/style based)
- Reddit API response caching
- Font preloading and caching
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import time
from typing import Optional, Dict, Any
from pathlib import Path

from .logger import get_logger

logger = get_logger(__name__)


class BackgroundCache:
    """Cache for generated background videos."""
    
    def __init__(self, cache_dir: str = "assets/cache/backgrounds"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_key(self, seconds: float, style: str, width: int, height: int) -> str:
        """Generate cache key for background video."""
        # Round seconds to avoid cache misses due to tiny differences
        rounded_seconds = round(seconds, 1)
        key_data = f"{rounded_seconds}_{style}_{width}_{height}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, seconds: float, style: str, width: int, height: int) -> Optional[str]:
        """Get cached background video path if it exists.
        
        Args:
            seconds: Duration of the background video
            style: Background style (gradient, radial, noise)
            width: Video width in pixels
            height: Video height in pixels
        
        Returns:
            Path to cached background video, or None if not cached
        """
        cache_key = self._get_cache_key(seconds, style, width, height)
        cache_path = os.path.join(self.cache_dir, f"bg_{cache_key}.mp4")
        
        if os.path.exists(cache_path):
            logger.debug(f"Background cache HIT: {cache_key} ({seconds}s, {style})")
            return cache_path
        
        logger.debug(f"Background cache MISS: {cache_key} ({seconds}s, {style})")
        return None
    
    def put(self, source_path: str, seconds: float, style: str, width: int, height: int) -> str:
        """Store background video in cache.
        
        Args:
            source_path: Path to the generated background video
            seconds: Duration of the background video
            style: Background style (gradient, radial, noise)
            width: Video width in pixels
            height: Video height in pixels
        
        Returns:
            Path to cached background video
        """
        cache_key = self._get_cache_key(seconds, style, width, height)
        cache_path = os.path.join(self.cache_dir, f"bg_{cache_key}.mp4")
        
        try:
            shutil.copyfile(source_path, cache_path)
            logger.debug(f"Background cached: {cache_key} ({seconds}s, {style})")
            return cache_path
        except Exception as e:
            logger.warning(f"Failed to cache background: {e}")
            return source_path
    
    def clear(self) -> int:
        """Clear all cached background videos.
        
        Returns:
            Number of files deleted
        """
        count = 0
        try:
            for file in os.listdir(self.cache_dir):
                if file.startswith("bg_") and file.endswith(".mp4"):
                    os.remove(os.path.join(self.cache_dir, file))
                    count += 1
            logger.info(f"Cleared {count} cached background videos")
        except Exception as e:
            logger.error(f"Failed to clear background cache: {e}")
        return count


class RedditCache:
    """Cache for Reddit API responses to reduce redundant fetches."""
    
    def __init__(self, cache_dir: str = "assets/cache/reddit", ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_path(self, thread_id: str) -> str:
        """Get cache file path for a thread ID."""
        return os.path.join(self.cache_dir, f"{thread_id}.json")
    
    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get cached Reddit thread data if available and not expired.
        
        Args:
            thread_id: Reddit thread ID
        
        Returns:
            Cached thread data dict, or None if not cached or expired
        """
        cache_path = self._get_cache_path(thread_id)
        
        if not os.path.exists(cache_path):
            logger.debug(f"Reddit cache MISS: {thread_id}")
            return None
        
        try:
            # Check if cache is expired
            file_age = time.time() - os.path.getmtime(cache_path)
            if file_age > self.ttl_seconds:
                logger.debug(f"Reddit cache EXPIRED: {thread_id} (age: {file_age:.0f}s)")
                os.remove(cache_path)
                return None
            
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            logger.debug(f"Reddit cache HIT: {thread_id} (age: {file_age:.0f}s)")
            return data
        except Exception as e:
            logger.warning(f"Failed to read Reddit cache for {thread_id}: {e}")
            return None
    
    def put(self, thread_id: str, data: Dict[str, Any]) -> None:
        """Store Reddit thread data in cache.
        
        Args:
            thread_id: Reddit thread ID
            data: Thread data to cache
        """
        cache_path = self._get_cache_path(thread_id)
        
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Reddit data cached: {thread_id}")
        except Exception as e:
            logger.warning(f"Failed to cache Reddit data for {thread_id}: {e}")
    
    def clear(self, older_than_seconds: Optional[int] = None) -> int:
        """Clear Reddit cache.
        
        Args:
            older_than_seconds: If provided, only delete entries older than this.
                               If None, delete all entries.
        
        Returns:
            Number of entries deleted
        """
        count = 0
        try:
            current_time = time.time()
            for file in os.listdir(self.cache_dir):
                if not file.endswith(".json"):
                    continue
                
                file_path = os.path.join(self.cache_dir, file)
                
                if older_than_seconds is None:
                    os.remove(file_path)
                    count += 1
                else:
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > older_than_seconds:
                        os.remove(file_path)
                        count += 1
            
            logger.info(f"Cleared {count} Reddit cache entries")
        except Exception as e:
            logger.error(f"Failed to clear Reddit cache: {e}")
        return count


class FontCache:
    """Preload and cache fonts for better performance."""
    
    def __init__(self):
        self._fonts: Dict[int, Any] = {}
    
    def preload_common_sizes(self) -> None:
        """Preload commonly used font sizes."""
        from .render_cards import _load_font
        
        common_sizes = [24, 28, 30, 32, 50]
        logger.debug(f"Preloading {len(common_sizes)} font sizes...")
        
        for size in common_sizes:
            try:
                font = _load_font(size)
                self._fonts[size] = font
            except Exception as e:
                logger.warning(f"Failed to preload font size {size}: {e}")
        
        logger.debug(f"Preloaded {len(self._fonts)} fonts")
    
    def get_font(self, size: int):
        """Get cached font or load it."""
        from .render_cards import _load_font
        
        if size not in self._fonts:
            self._fonts[size] = _load_font(size)
        
        return self._fonts[size]
