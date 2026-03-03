import os
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("formatter")

INPUT_FILE = "/data/prioritized.txt"
OUTPUT_FILE = "/output/daily_digest.md"

def format_to_markdown():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    today = datetime.now().strftime('%Y-%m-%d')

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("# Your Daily AI Digest\n\n")
        out.write(f"**Date:** {today}\n\n")
        out.write("## Top Insights\n\n")
        for line in lines:
            if '] ' in line:
                score = line.split(']')[0][1:]
                content = line.split('] ', 1)[1]
                out.write(f"- **Priority {score}**: {content}\n")
            else:
                out.write(f"- {line}\n")

    logger.info(f"Digest written to {OUTPUT_FILE}")

if __name__ == "__main__":
    format_to_markdown()