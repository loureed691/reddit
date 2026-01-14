import argparse
import json
import os
from pathlib import Path

from src.factory import FactoryConfig, RedditVideoFactory
from src.automation import RedditSearcher, ProducedVideosTracker

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
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg_raw = json.load(f)

    cfg = FactoryConfig.from_dict(cfg_raw)

    # Apply command-line overrides
    if args.comments is not None:
        cfg.settings.max_comments = int(args.comments)
    if args.lang:
        cfg.settings.language = args.lang.strip()
    if args.background:
        cfg.settings.background.background_path = args.background
    if args.duration_mode:
        cfg.settings.video_duration.mode = args.duration_mode

    # Automated mode
    if args.auto or (cfg.automation.enabled and not args.url):
        print("Running in automated mode...")
        
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
            print("No suitable posts found. Exiting.")
            return
        
        print(f"\nProducing video for: {post.title}")
        print(f"URL: {post.url}\n")
        
        # Create the video
        factory = RedditVideoFactory(cfg)
        out = factory.make_from_url(post.url, keep_temp=args.keep_temp)
        
        # Mark as produced
        tracker.mark_produced(post.thread_id)
        
        print(f"\nDONE: {out}\n")
        print(f"Thread {post.thread_id} marked as produced.")
        
    else:
        # Manual mode - requires URL
        if not args.url:
            print("Error: --url is required when not in automated mode")
            print("Use --auto flag to run in automated mode, or provide --url")
            return
        
        factory = RedditVideoFactory(cfg)
        out = factory.make_from_url(args.url, keep_temp=args.keep_temp)
        print(f"\nDONE: {out}\n")

if __name__ == "__main__":
    main()
