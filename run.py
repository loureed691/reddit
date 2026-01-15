import argparse
import json
import os
from pathlib import Path

from src.factory import FactoryConfig, RedditVideoFactory
from src.automation import RedditSearcher, ProducedVideosTracker
from src.logger import setup_logging, get_logger
from src.config import _validate_log_level

def main():
    ap = argparse.ArgumentParser(description="Reddit Video Factory (standalone).")
    ap.add_argument("--url", default=None, help="Reddit thread URL (or just the thread id)")
    ap.add_argument("--comments", type=int, default=None, help="Number of comments to include")
    ap.add_argument("--lang", default=None, help="Language hint for text layout (en/de/...)")
    ap.add_argument("--background", default=None, help="Path to background.mp4 to use instead of auto-gen")
    ap.add_argument("--config", default="config.json", help="Path to config.json")
    ap.add_argument("--keep-temp", action="store_true", help="Keep assets/temp/<thread_id> for debugging")
    ap.add_argument("--auto", action="store_true", help="Run in automated mode (search for posts automatically)")
    ap.add_argument("--duration-mode", choices=["short", "long"], default=None, 
                   help="Override video duration mode: 'short' (1-2 min) or 'long' (60 min)")
    ap.add_argument("--log-level", default=None, help="Override log level (DEBUG, INFO, WARNING, ERROR)")
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg_raw = json.load(f)

    cfg = FactoryConfig.from_dict(cfg_raw)
    
    # Setup logging early with configuration from config file
    # Apply command-line log level override if provided
    if args.log_level:
        cfg.logging.log_level = _validate_log_level(args.log_level, "INFO")
    
    setup_logging(cfg.logging)
    
    logger = get_logger(__name__)
    logger.info("Reddit Video Factory started")
    logger.debug(f"Configuration loaded from: {args.config}")

    # Apply command-line overrides
    if args.comments is not None:
        cfg.settings.max_comments = int(args.comments)
        logger.debug(f"Max comments overridden to: {args.comments}")
    if args.lang:
        cfg.settings.language = args.lang.strip()
        logger.debug(f"Language overridden to: {args.lang}")
    if args.background:
        cfg.settings.background.background_path = args.background
        logger.debug(f"Background path overridden to: {args.background}")
    if args.duration_mode:
        cfg.settings.video_duration.mode = args.duration_mode
        logger.debug(f"Duration mode overridden to: {args.duration_mode}")

    # Automated mode
    if args.auto or (cfg.automation.enabled and not args.url):
        logger.info("Running in automated mode")
        
        # Initialize automation components
        tracker = ProducedVideosTracker(cfg.automation.produced_videos_db)
        searcher = RedditSearcher(cfg.reddit.user_agent, timeout=cfg.automation.request_timeout)
        
        # Find a suitable post
        post = searcher.find_suitable_post(
            subreddits=cfg.automation.subreddits,
            tracker=tracker,
            sort_by=cfg.automation.sort_by,
            time_filter=cfg.automation.time_filter,
            min_score=cfg.automation.min_score,
            min_comments=cfg.automation.min_comments,
        )
        
        if not post:
            logger.warning("No suitable posts found. Exiting.")
            return
        
        logger.info(f"Producing video for: {post.title}")
        logger.info(f"URL: {post.url}")
        logger.debug(f"Post details - Score: {post.score}, Comments: {post.num_comments}, Subreddit: r/{post.subreddit}")
        
        # Create the video
        factory = RedditVideoFactory(cfg)
        try:
            out = factory.make_from_url(post.url, keep_temp=args.keep_temp)
            
            # Mark as produced only on success
            tracker.mark_produced(post.thread_id)
            
            logger.info(f"Video created successfully: {out}")
            logger.info(f"Thread {post.thread_id} marked as produced")
        except Exception as e:
            logger.error(f"Failed to create video: {e}", exc_info=True)
            logger.warning(f"Thread {post.thread_id} NOT marked as produced (will retry next run)")
            return
        
    else:
        # Manual mode - requires URL
        if not args.url:
            logger.error("--url is required when not in automated mode")
            logger.info("Use --auto flag to run in automated mode, or provide --url")
            return
        
        logger.info(f"Running in manual mode with URL: {args.url}")
        factory = RedditVideoFactory(cfg)
        try:
            out = factory.make_from_url(args.url, keep_temp=args.keep_temp)
            logger.info(f"Video created successfully: {out}")
        except Exception as e:
            logger.error(f"Failed to create video: {e}", exc_info=True)
            return

if __name__ == "__main__":
    main()
