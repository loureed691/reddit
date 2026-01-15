# Sophisticated Logging System

This Reddit Video Factory now includes a sophisticated logging system with the following features:

## Features

### 1. **Multi-Level Logging**
- **DEBUG**: Detailed information for debugging (file only by default)
- **INFO**: General informational messages (console and file)
- **WARNING**: Warning messages for potential issues (console and file)
- **ERROR**: Error messages with full tracebacks (console and file)
- **CRITICAL**: Critical errors (console and file)

### 2. **Dual Output Handlers**
- **Console Handler**: Rich-formatted output for user-facing messages with colors and pretty tracebacks
- **File Handler**: Detailed logs with timestamps, module names, function names, and line numbers

### 3. **Rotating File Logs**
- Automatic log rotation when file reaches 10MB (configurable)
- Keeps up to 5 backup files (configurable)
- Logs stored in `logs/reddit_factory.log`

### 4. **Contextual Information**
File logs include:
- Timestamp (YYYY-MM-DD HH:MM:SS)
- Log level
- Module name
- Function name
- Line number
- Message

Example:
```
2026-01-15 01:58:49 | DEBUG | src.factory:make_from_url:139 | Fetching thread abc123
2026-01-15 01:58:50 | INFO  | src.factory:make_from_url:225 | Selected 8 comments for target duration
```

### 5. **Rich Console Output**
Console output uses the Rich library for:
- Color-coded log levels
- Pretty exception tracebacks with syntax highlighting
- Timestamps
- Clean, readable formatting

### 6. **Configurable Settings**
All logging settings can be configured in `config.json`:

```json
{
  "logging": {
    "log_level": "DEBUG",           // Root log level (DEBUG, INFO, WARNING, ERROR)
    "console_level": "INFO",        // Console output level
    "file_level": "DEBUG",          // File output level
    "log_dir": "logs",              // Directory for log files
    "log_file": "reddit_factory.log", // Log file name
    "max_bytes": 10485760,          // Max log file size (10MB)
    "backup_count": 5,              // Number of backup files to keep
    "enable_file_logging": true,    // Enable/disable file logging
    "enable_console_logging": true  // Enable/disable console logging
  }
}
```

## Usage

### Command-Line Override
You can override the log level from the command line:

```bash
# Run with DEBUG logging
python run.py --log-level DEBUG --url https://reddit.com/...

# Run with ERROR logging only
python run.py --log-level ERROR --auto
```

### In Code
```python
from src.logger import get_logger

logger = get_logger(__name__)

logger.debug("This appears in file only (by default)")
logger.info("This appears in both console and file")
logger.warning("Warning message")
logger.error("Error message", exc_info=True)  # Includes traceback
```

## Log Locations

- **Development/Debugging**: Set `log_level` to `DEBUG` to capture all details in the log file
- **Production**: Set `log_level` to `INFO` for normal operation
- **Troubleshooting**: Check `logs/reddit_factory.log` for detailed error information

## Benefits

1. **Debugging**: DEBUG logs help trace issues without cluttering the console
2. **Monitoring**: INFO logs show progress and key operations
3. **Error Tracking**: Full exception tracebacks are preserved in log files
4. **Performance**: Console stays clean while file captures everything
5. **Auditing**: All operations are logged with timestamps for review
6. **Rotation**: Old logs are automatically archived, preventing disk space issues

## Examples

### Console Output (INFO level)
```
[01/15/26 01:58:49] INFO     Reddit Video Factory started
                    INFO     Fetching thread: abc123
                    INFO     Target video duration: 90s (short mode)
                    INFO     Rendering cards...
                    INFO     Generating TTS audio...
                    INFO     Selected 8 comments for target duration
                    INFO     Preparing background...
                    INFO     Assembling final video...
                    INFO     Video created successfully: results/AskReddit/video.mp4
```

### File Log Output (DEBUG level)
```
2026-01-15 01:58:49 | DEBUG    | src.logger:setup_logging:146 | Logging configured: console_level=INFO, file_level=DEBUG
2026-01-15 01:58:49 | INFO     | __main__:main:44 | Reddit Video Factory started
2026-01-15 01:58:49 | DEBUG    | __main__:main:45 | Configuration loaded from: config.json
2026-01-15 01:58:50 | INFO     | src.factory:make_from_url:139 | Fetching thread: abc123
2026-01-15 01:58:50 | DEBUG    | src.reddit_fetcher:fetch_thread:61 | Fetching thread abc123 with max_comments=12, prefer_top=True
2026-01-15 01:58:51 | INFO     | src.reddit_fetcher:fetch_thread:104 | Fetched thread: 8 comments from r/AskReddit
```

## Testing

Run the test script to see the logging system in action:

```bash
python test_logging.py
```

This will demonstrate:
- Different log levels
- Console vs. file output differences
- Exception logging with tracebacks
- Module-specific loggers
