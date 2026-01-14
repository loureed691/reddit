import argparse
import json
import os
from pathlib import Path

from src.factory import FactoryConfig, RedditVideoFactory

def main():
    ap = argparse.ArgumentParser(description="Reddit Video Factory (standalone).")
    ap.add_argument("--url", required=True, help="Reddit thread URL (or just the thread id)")
    ap.add_argument("--comments", type=int, default=None, help="Number of comments to include")
    ap.add_argument("--lang", default=None, help="Language hint for text layout (en/de/...)")
    ap.add_argument("--background", default=None, help="Path to background.mp4 to use instead of auto-gen")
    ap.add_argument("--config", default="config.json", help="Path to config.json")
    ap.add_argument("--keep-temp", action="store_true", help="Keep assets/temp/<thread_id> for debugging")
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg_raw = json.load(f)

    cfg = FactoryConfig.from_dict(cfg_raw)

    if args.comments is not None:
        cfg.settings.max_comments = int(args.comments)
    if args.lang:
        cfg.settings.language = args.lang.strip()
    if args.background:
        cfg.settings.background.background_path = args.background

    factory = RedditVideoFactory(cfg)
    out = factory.make_from_url(args.url, keep_temp=args.keep_temp)
    print(f"\nDONE: {out}\n")

if __name__ == "__main__":
    main()
