# AGENTS.md - Reddit Monitor for FirstMover

## What This Does

Monitors NYC apartment-related subreddits for posts where FirstMover would be genuinely helpful. Filters with GPT-4o-mini to find high-quality opportunities, then surfaces them to Discord for human review.

## Architecture

```
Every 15 min (OpenClaw cron):
  ├─ Fetch new posts/comments from target subreddits
  ├─ Filter: only posts from last 20 minutes
  ├─ Filter: skip roommate/sublet posts
  ├─ Filter: GPT-4o-mini evaluates relevance to FirstMover
  └─ Post opportunities to Discord #firstmover-reddit-alerts
      └─ Each post gets a thread with a draft reply
```

## Files

| File | Purpose |
|------|---------|
| `monitor.py` | Main script - fetches Reddit, filters, outputs results |
| `reply_style.md` | Tone guide for draft replies (human, helpful, not salesy) |
| `seen_posts.json` | State - tracks processed post IDs to avoid duplicates |
| `relevant_posts.json` | Output - latest filtered results |

## Config (in monitor.py)

```python
SUBREDDITS = ["NYCapartments", "movingtoNYC", "brooklyn", "astoria"]
MAX_AGE_MINUTES = 20  # Only process recent posts
SKIP_KEYWORDS = ["roommate", "sublet", ...]  # Cheap pre-filter
```

## Environment Variables

| Var | Required | Purpose |
|-----|----------|---------|
| `OPENAI_API_KEY` | Yes | GPT-4o-mini for relevance filtering |

## Running Locally

```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Run once
python3 monitor.py

# Output goes to stdout + relevant_posts.json
```

## Modifying

**Adding subreddits:** Edit `SUBREDDITS` list in monitor.py

**Adjusting time window:** Edit `MAX_AGE_MINUTES`

**Changing skip words:** Edit `SKIP_KEYWORDS`

**Changing LLM prompt:** Edit the `llm_filter()` function prompt

## After Any Changes

```bash
git add -A && git commit -m "description of change" && git push
```

The cron job runs from the local workspace, but keeping GitHub in sync lets Ben see all changes.

## Discord Integration

Results go to Discord channel `1468612002820919377` (#firstmover-reddit-alerts).

Format:
1. Alert message with subreddit, time, URL, and post summary
2. Reply to that message with draft Reddit comment (following reply_style.md)

## Cost

~$0.04/day for GPT-4o-mini filtering (~$1.20/month)
