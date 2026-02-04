#!/bin/bash
# Run Reddit monitor and output results for OpenClaw to process

cd "$(dirname "$0")"

# Run the monitor
python3 monitor.py > /tmp/reddit_monitor_output.txt 2>&1
exit_code=$?

# If we found relevant posts (exit code 1), output them
if [ $exit_code -eq 1 ]; then
    echo "REDDIT_MONITOR_RESULTS"
    cat /tmp/reddit_monitor_output.txt
    
    # Also output the JSON for structured processing
    if [ -f relevant_posts.json ]; then
        echo ""
        echo "JSON_DATA:"
        cat relevant_posts.json
    fi
fi
