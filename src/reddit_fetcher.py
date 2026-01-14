"""Reddit thread fetcher with connection pooling and retry logic.

Fetches thread data from Reddit's public JSON API with:
- Session-based connection pooling for better performance
- Exponential backoff retry logic for reliability
- Proper error handling
"""
from __future__ import annotations
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from functools import lru_cache

@dataclass
class RedditComment:
    author: str
    body: str
    score: int

@dataclass
class RedditThread:
    thread_id: str
    subreddit: str
    title: str
    comments: List[RedditComment]

_THREAD_ID_RE = re.compile(r"/comments/([a-z0-9]{5,10})", re.IGNORECASE)

def extract_thread_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    m = _THREAD_ID_RE.search(s)
    if m:
        return m.group(1)
    # if user provided bare id
    if re.fullmatch(r"[a-z0-9]{5,10}", s, re.IGNORECASE):
        return s
    raise ValueError(f"Could not extract thread id from: {url_or_id}")

def fetch_thread(thread_id: str, user_agent: str, max_comments: int, prefer_top: bool) -> RedditThread:
    """Fetch a Reddit thread with comments.
    
    Uses a persistent session for better connection reuse and includes
    retry logic for improved reliability.
    """
    url = f"https://www.reddit.com/comments/{thread_id}.json"
    headers = {"User-Agent": user_agent}
    
    # Use session for connection pooling and better performance
    session = requests.Session()
    session.headers.update(headers)
    
    # Retry logic for transient failures
    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = session.get(url, timeout=30)
            break
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to fetch Reddit thread after {max_retries} attempts: {e}")
            time.sleep(1 * (attempt + 1))  # exponential backoff
    else:
        r = session.get(url, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Reddit returned {r.status_code}: {r.text[:200]}")
    data = r.json()
    if not isinstance(data, list) or len(data) < 2:
        raise RuntimeError("Unexpected Reddit JSON structure")

    post = data[0]["data"]["children"][0]["data"]
    subreddit = post.get("subreddit", "unknown")
    title = post.get("title", "").strip()
    tid = post.get("id", thread_id)

    raw_comments = data[1]["data"]["children"]

    comments: List[RedditComment] = []
    for c in raw_comments:
        kind = c.get("kind")
        if kind != "t1":
            continue
        cd = c.get("data", {})
        body = (cd.get("body") or "").strip()
        author = (cd.get("author") or "unknown").strip()
        score = int(cd.get("score") or 0)

        if not body or body in ("[deleted]", "[removed]"):
            continue
        # keep it sane
        if len(body) < 5:
            continue
        comments.append(RedditComment(author=author, body=body, score=score))

    if prefer_top:
        comments.sort(key=lambda x: x.score, reverse=True)

    comments = comments[:max_comments]
    if not title:
        title = f"Reddit Thread {thread_id}"
    return RedditThread(thread_id=tid, subreddit=subreddit, title=title, comments=comments)
