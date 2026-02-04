#!/usr/bin/env python3
"""
Reddit Monitor for FirstMover
Polls target subreddits for posts/comments relevant to NYC apartment hunting.
"""

import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# OpenAI API for LLM filtering
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
USE_LLM_FILTER = bool(OPENAI_API_KEY)

# Config
SUBREDDITS = [
    "NYCapartments",
    "movingtoNYC",
    "brooklyn",
    "astoria",
]

# Only process posts from the last N minutes (matches cron interval + buffer)
MAX_AGE_MINUTES = 120

# Keywords that suggest the post might be relevant (more specific to avoid false positives)
KEYWORDS = [
    "streeteasy", "street easy",
    "apartment hunting", "apartment search", "apartment hunt",
    "new listing", "new listings",
    "notifications for", "get notified", "set up alerts",
    "be the first", "act fast", "move fast", "first to respond", "first to inquire",
    "how do i find apartments", "how to find apartments", "tips for finding",
    "looking for an apartment", "looking for a place to rent",
    "broker fee", "no fee apartment",
    "moving to nyc soon", "relocating to nyc", "moving to new york",
    "apartment tips", "rental search tips",
    "refreshing streeteasy", "checking streeteasy", "streeteasy notifications",
    "competitive rental", "competitive market",
    "beat other applicants", "getting outbid",
]

# Negative keywords - skip these
SKIP_KEYWORDS = [
    "roommate", "room for rent", "looking for roommate",
    "sublease", "sublet",
]

STATE_FILE = Path(__file__).parent / "seen_posts.json"
OUTPUT_FILE = Path(__file__).parent / "relevant_posts.json"

def llm_filter(posts: list) -> list:
    """Use GPT-4o-mini to filter posts for true relevance."""
    if not posts or not USE_LLM_FILTER:
        return posts
    
    print(f"Running LLM filter on {len(posts)} posts...")
    
    # Batch posts for efficiency
    posts_text = []
    for i, p in enumerate(posts):
        title = p.get('title', '') or ''
        text = p.get('text', '')[:300]
        posts_text.append(f"[{i}] {title} | {text}")
    
    prompt = f"""You are filtering Reddit posts for FirstMover, an app that sends INSTANT push notifications when new apartments hit StreetEasy.

BE VERY STRICT. Only select posts where the person would DIRECTLY benefit from getting listing alerts faster. 

GOOD (select these):
- "ISO apartment" or "Looking for apartment" posts with budget/neighborhood - ACTIVELY HUNTING
- "How do I find apartments before they're gone?" - WANTS TO BE FASTER
- "StreetEasy notifications suck" or "listings disappear so fast" - FRUSTRATED WITH SPEED
- "Tips for apartment hunting?" where speed/timing is relevant

BAD (reject these):
- Already found/have an apartment
- Asking about rent prices, neighborhoods, landlords, policies, leases
- Giving advice to others (not searching themselves)  
- Moving company questions
- Roommate/sublet posts
- Bedbug, maintenance, legal questions
- General NYC discussion
- Someone mentioning StreetEasy in passing

When in doubt, reject. We only want HIGH-QUALITY opportunities where FirstMover is genuinely relevant.

Reply with ONLY index numbers of GOOD posts (comma-separated), or NONE if no good matches.

Posts:
{chr(10).join(posts_text)}

Indices:"""

    try:
        req_data = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100,
            "temperature": 0
        }).encode()
        
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=req_data,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            response_text = result["choices"][0]["message"]["content"].strip()
            
            print(f"LLM response: {response_text}")
            
            if response_text.upper() == "NONE":
                return []
            
            # Parse indices
            try:
                indices = [int(x.strip()) for x in response_text.replace(" ", "").split(",") if x.strip().isdigit()]
                filtered = [posts[i] for i in indices if i < len(posts)]
                print(f"LLM kept {len(filtered)}/{len(posts)} posts")
                return filtered
            except:
                print("Failed to parse LLM response, returning all posts")
                return posts
                
    except Exception as e:
        print(f"LLM filter error: {e}")
        return posts  # Fall back to keyword-filtered posts

def load_seen():
    """Load previously seen post IDs."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    """Save seen post IDs."""
    # Keep only last 5000 to prevent unbounded growth
    recent = list(seen)[-5000:]
    with open(STATE_FILE, "w") as f:
        json.dump(recent, f)

def fetch_subreddit(subreddit: str, limit: int = 50) -> list:
    """Fetch recent posts from a subreddit."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
    headers = {"User-Agent": "FirstMoverBot/1.0"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("data", {}).get("children", [])
    except Exception as e:
        print(f"Error fetching r/{subreddit}: {e}")
        return []

def fetch_comments(subreddit: str, limit: int = 100) -> list:
    """Fetch recent comments from a subreddit."""
    url = f"https://www.reddit.com/r/{subreddit}/comments.json?limit={limit}"
    headers = {"User-Agent": "FirstMoverBot/1.0"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("data", {}).get("children", [])
    except Exception as e:
        print(f"Error fetching r/{subreddit} comments: {e}")
        return []

def is_relevant(text: str) -> tuple[bool, list]:
    """Pre-filter: skip obvious non-matches, let LLM handle the rest."""
    text_lower = text.lower()
    
    # Skip if contains negative keywords (cheap filter for obvious misses)
    for kw in SKIP_KEYWORDS:
        if kw in text_lower:
            return False, []
    
    # Pass everything else to LLM for evaluation
    # (Keywords kept for logging/debugging but not required)
    matched = []
    for kw in KEYWORDS:
        if kw in text_lower:
            matched.append(kw)
    
    return True, matched  # Let LLM decide relevance

def process_post(post_data: dict, post_type: str = "post") -> dict | None:
    """Process a single post/comment and return if relevant."""
    data = post_data.get("data", {})
    post_id = data.get("id", "")
    
    # Skip posts older than MAX_AGE_MINUTES
    created_utc = data.get("created_utc", 0)
    now_utc = datetime.now(timezone.utc).timestamp()
    age_minutes = (now_utc - created_utc) / 60
    
    if age_minutes > MAX_AGE_MINUTES:
        return None
    
    # Get text content
    if post_type == "post":
        text = f"{data.get('title', '')} {data.get('selftext', '')}"
    else:
        text = data.get("body", "")
    
    relevant, keywords = is_relevant(text)
    if not relevant:
        return None
    
    return {
        "id": post_id,
        "type": post_type,
        "subreddit": data.get("subreddit", ""),
        "title": data.get("title", "") if post_type == "post" else None,
        "text": text[:500],  # Truncate for readability
        "author": data.get("author", ""),
        "url": f"https://reddit.com{data.get('permalink', '')}",
        "created_utc": data.get("created_utc", 0),
        "matched_keywords": keywords,
        "score": data.get("score", 0),
    }

def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting Reddit monitor...")
    
    seen = load_seen()
    relevant_posts = []
    new_seen = set()
    
    for subreddit in SUBREDDITS:
        # Fetch posts
        posts = fetch_subreddit(subreddit)
        for post in posts:
            post_id = post.get("data", {}).get("id", "")
            full_id = f"post_{post_id}"
            new_seen.add(full_id)
            
            if full_id in seen:
                continue
            
            result = process_post(post, "post")
            if result:
                relevant_posts.append(result)
        
        # Fetch comments
        comments = fetch_comments(subreddit)
        for comment in comments:
            comment_id = comment.get("data", {}).get("id", "")
            full_id = f"comment_{comment_id}"
            new_seen.add(full_id)
            
            if full_id in seen:
                continue
            
            result = process_post(comment, "comment")
            if result:
                relevant_posts.append(result)
    
    # Update seen set
    seen.update(new_seen)
    save_seen(seen)
    
    # Sort by created time, newest first
    relevant_posts.sort(key=lambda x: x.get("created_utc", 0), reverse=True)
    
    # LLM filter for better precision
    if relevant_posts:
        relevant_posts = llm_filter(relevant_posts)
    
    # Save relevant posts
    if relevant_posts:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(relevant_posts, f, indent=2)
        print(f"Found {len(relevant_posts)} relevant posts/comments")
        
        # Output summary for immediate use
        for post in relevant_posts[:10]:  # Top 10
            print(f"\n{'='*60}")
            print(f"[{post['type'].upper()}] r/{post['subreddit']}")
            if post.get('title'):
                print(f"Title: {post['title'][:100]}")
            print(f"Keywords: {', '.join(post['matched_keywords'])}")
            print(f"URL: {post['url']}")
            print(f"Text preview: {post['text'][:200]}...")
    else:
        print("No new relevant posts found")
    
    return relevant_posts

if __name__ == "__main__":
    results = main()
    # Exit with code 0 if no results, 1 if there are results (for easy scripting)
    exit(0 if not results else 1)
