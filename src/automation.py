"""Automation module for Reddit video factory.

This module provides functionality to:
1. Automatically search for suitable Reddit posts
2. Track produced videos to avoid duplicates
3. Filter posts based on configurable criteria
"""
from __future__ import annotations
import json
import os
import shutil
import tempfile
from typing import List, Optional, Set
from dataclasses import dataclass

import requests
from rich.console import Console

console = Console()

@dataclass
class RedditPost:
    """Represents a Reddit post suitable for video creation."""
    thread_id: str
    subreddit: str
    title: str
    score: int
    num_comments: int
    url: str

class ProducedVideosTracker:
    """Tracks which Reddit posts have already been converted to videos."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.produced_ids: Set[str] = self._load()
    
    def _load(self) -> Set[str]:
        """Load the set of produced video IDs from disk."""
        if not os.path.exists(self.db_path):
            return set()
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("produced_ids", []))
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load produced videos database: {e}[/yellow]")
            return set()
    
    def _save(self) -> None:
        """Save the set of produced video IDs to disk atomically."""
        try:
            # Write to a temporary file first
            dir_path = os.path.dirname(self.db_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            with tempfile.NamedTemporaryFile(mode='w', dir=dir_path or '.', delete=False, suffix='.tmp') as tmp:
                json.dump({"produced_ids": sorted(list(self.produced_ids))}, tmp, indent=2)
                tmp_path = tmp.name
            
            # Atomically move the temp file to the target location
            shutil.move(tmp_path, self.db_path)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not save produced videos database: {e}[/yellow]")
    
    def is_produced(self, thread_id: str) -> bool:
        """Check if a video has already been produced for this thread."""
        return thread_id in self.produced_ids
    
    def mark_produced(self, thread_id: str) -> None:
        """Mark a thread as having been produced."""
        self.produced_ids.add(thread_id)
        self._save()

class RedditSearcher:
    """Searches Reddit for suitable posts to convert to videos."""
    
    def __init__(self, user_agent: str, timeout: int = 30):
        self.user_agent = user_agent
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
    
    def search_posts(
        self,
        subreddit: str,
        sort_by: str = "hot",
        time_filter: str = "day",
        min_score: int = 1000,
        min_comments: int = 50,
        limit: int = 25,
    ) -> List[RedditPost]:
        """Search for posts in a subreddit that meet the criteria.
        
        Args:
            subreddit: Name of the subreddit to search
            sort_by: Sort method (hot, top, new)
            time_filter: Time filter for 'top' sort (hour, day, week, month, year, all)
            min_score: Minimum post score
            min_comments: Minimum number of comments
            limit: Maximum number of posts to retrieve
            
        Returns:
            List of RedditPost objects that meet the criteria
        """
        # Build the URL based on sort type
        if sort_by == "top":
            url = f"https://www.reddit.com/r/{subreddit}/top.json?t={time_filter}&limit={limit}"
        elif sort_by == "new":
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
        else:  # hot
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            console.print(f"[red]Error fetching posts from r/{subreddit}: {e}[/red]")
            return []
        
        posts: List[RedditPost] = []
        children = data.get("data", {}).get("children", [])
        
        for child in children:
            post_data = child.get("data", {})
            
            # Skip if not a text post (we want discussion threads)
            if post_data.get("is_self") is False:
                continue
            
            thread_id = post_data.get("id", "")
            title = post_data.get("title", "").strip()
            score = int(post_data.get("score", 0))
            num_comments = int(post_data.get("num_comments", 0))
            subreddit_name = post_data.get("subreddit", subreddit)
            permalink = post_data.get("permalink", "")
            
            # Apply filters
            if score < min_score:
                continue
            if num_comments < min_comments:
                continue
            if not title or not thread_id:
                continue
            
            posts.append(RedditPost(
                thread_id=thread_id,
                subreddit=subreddit_name,
                title=title,
                score=score,
                num_comments=num_comments,
                url=f"https://www.reddit.com{permalink}"
            ))
        
        return posts
    
    def find_suitable_post(
        self,
        subreddits: List[str],
        tracker: ProducedVideosTracker,
        sort_by: str = "hot",
        time_filter: str = "day",
        min_score: int = 1000,
        min_comments: int = 50,
    ) -> Optional[RedditPost]:
        """Find the first suitable post that hasn't been produced yet.
        
        Searches through the list of subreddits in order until a suitable
        post is found that hasn't been produced yet.
        
        Returns:
            RedditPost if found, None otherwise
        """
        for subreddit in subreddits:
            console.print(f"[cyan]Searching r/{subreddit}...[/cyan]")
            posts = self.search_posts(
                subreddit=subreddit,
                sort_by=sort_by,
                time_filter=time_filter,
                min_score=min_score,
                min_comments=min_comments,
            )
            
            for post in posts:
                if not tracker.is_produced(post.thread_id):
                    console.print(f"[green]Found suitable post: {post.title[:60]}...[/green]")
                    console.print(f"[dim]Score: {post.score}, Comments: {post.num_comments}[/dim]")
                    return post
                else:
                    console.print(f"[dim]Skipping already produced: {post.title[:60]}...[/dim]")
        
        console.print("[yellow]No suitable posts found that haven't been produced.[/yellow]")
        return None
