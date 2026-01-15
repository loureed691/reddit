"""Sophisticated logging module for Reddit Video Factory.

This module provides centralized logging configuration with:
- Structured logging with multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Console output with rich formatting for user-facing messages
- File logging with rotation for persistent debugging
- Configurable log levels per handler
- Context-aware logging with timestamps, module names, and line numbers

Usage:
    from src.logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("Processing started")
    logger.warning("Something might be wrong")
    logger.error("An error occurred", exc_info=True)
"""
from __future__ import annotations
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from rich.logging import RichHandler
from rich.console import Console

# Global console for rich output
console = Console()

# Track if logging has been configured
_logging_configured = False


class LogConfig:
    """Configuration for logging system."""
    
    def __init__(
        self,
        log_level: str = "INFO",
        console_level: str = "INFO",
        file_level: str = "DEBUG",
        log_dir: str = "logs",
        log_file: str = "reddit_factory.log",
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        enable_file_logging: bool = True,
        enable_console_logging: bool = True,
    ):
        # Validate log levels
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        
        self.log_level = log_level.upper() if log_level.upper() in valid_levels else "INFO"
        self.console_level = console_level.upper() if console_level.upper() in valid_levels else "INFO"
        self.file_level = file_level.upper() if file_level.upper() in valid_levels else "DEBUG"
        self.log_dir = log_dir
        self.log_file = log_file
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.enable_file_logging = enable_file_logging
        self.enable_console_logging = enable_console_logging
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> LogConfig:
        """Create LogConfig from dictionary."""
        return cls(
            log_level=config_dict.get("log_level", "INFO"),
            console_level=config_dict.get("console_level", "INFO"),
            file_level=config_dict.get("file_level", "DEBUG"),
            log_dir=config_dict.get("log_dir", "logs"),
            log_file=config_dict.get("log_file", "reddit_factory.log"),
            max_bytes=config_dict.get("max_bytes", 10 * 1024 * 1024),
            backup_count=config_dict.get("backup_count", 5),
            enable_file_logging=config_dict.get("enable_file_logging", True),
            enable_console_logging=config_dict.get("enable_console_logging", True),
        )


def setup_logging(config: Optional[LogConfig] = None) -> None:
    """Configure the logging system with handlers and formatters.
    
    This should be called once at application startup. It sets up:
    1. Rich console handler for user-facing output (INFO and above)
    2. Rotating file handler for detailed debugging (DEBUG and above)
    
    Args:
        config: LogConfig instance with logging settings. If None, uses defaults.
    """
    global _logging_configured
    
    if _logging_configured:
        return
    
    if config is None:
        config = LogConfig()
    
    # Get root logger and set base level
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level, logging.DEBUG))
    
    # Clear any existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Detailed formatter for file logs
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Simple formatter for console (Rich handles its own formatting)
    simple_formatter = logging.Formatter('%(message)s')
    
    # Console handler with Rich formatting
    if config.enable_console_logging:
        console_handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            markup=True,
            show_time=True,
            show_level=True,
            show_path=False,
            tracebacks_show_locals=False,
        )
        console_handler.setLevel(getattr(logging, config.console_level, logging.INFO))
        console_handler.setFormatter(simple_formatter)
        root_logger.addHandler(console_handler)
    
    # File handler with rotation
    log_file_path = None
    if config.enable_file_logging:
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_path = log_dir / config.log_file
        log_file_path = log_path
        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(getattr(logging, config.file_level, logging.DEBUG))
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)
    
    _logging_configured = True
    
    # Log that logging has been configured
    logger = logging.getLogger(__name__)
    logger.debug(f"Logging configured: console_level={config.console_level}, file_level={config.file_level}")
    if log_file_path:
        logger.debug(f"Log file: {log_file_path}")
    else:
        logger.debug("File logging disabled")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name.
    
    Args:
        name: Module name (typically __name__)
    
    Returns:
        Configured logger instance
    
    Example:
        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    # Ensure logging is configured with defaults if not already done
    if not _logging_configured:
        setup_logging()
    
    return logging.getLogger(name)


# Convenience function for backward compatibility with existing console usage
def get_console() -> Console:
    """Get the rich Console instance for direct use if needed."""
    return console
