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
MAX_DISPLAY_FINDINGS = int(os.getenv("MAX_DISPLAY_FINDINGS", "4"))
MAX_DISPLAY_ACTIONS = int(os.getenv("MAX_DISPLAY_ACTIONS", "3"))


def parse_prioritized_line(line):
    if "] " in line and line.startswith("["):
        score = line.split("]")[0][1:]
        content = line.split("] ", 1)[1].strip()
    else:
        score = "0"
        content = line.strip()

    if content.startswith("- "):
        content = content[2:].strip()
    elif content.startswith("•"):
        content = content.lstrip("•").strip()
    return score, content


def parse_finding(content):
    if not content.upper().startswith("FINDING:"):
        return None

    payload = content.split(":", 1)[1].strip()
    fields = {}
    for part in payload.split("|"):
        fragment = part.strip()
        if "=" not in fragment:
            continue
        key, value = fragment.split("=", 1)
        fields[key.strip().lower()] = value.strip()

    if "severity" not in fields or "source" not in fields or "error" not in fields:
        return None
    return fields

def format_to_markdown():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    today = datetime.now().strftime('%Y-%m-%d')

    parsed = [parse_prioritized_line(line) for line in lines]

    recap = ""
    for _, content in parsed:
        if content.upper().startswith("LOG_RECAP:"):
            recap = content
            break

    compact_findings = []
    actions = []
    seen_findings = set()
    seen_actions = set()

    for score, content in parsed:
        finding = parse_finding(content)
        if not finding:
            continue

        key = (
            finding.get("severity", ""),
            finding.get("source", ""),
            finding.get("error", ""),
        )
        if key not in seen_findings and len(compact_findings) < MAX_DISPLAY_FINDINGS:
            compact_findings.append(
                f"P{score} | {finding['severity']} | {finding['source']} | "
                f"{finding['error']}"
            )
            seen_findings.add(key)

        action = finding.get("action", "")
        if action and action not in seen_actions and len(actions) < MAX_DISPLAY_ACTIONS:
            actions.append(action)
            seen_actions.add(action)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("# AI Log Recap\n\n")
        out.write(f"**Date:** {today}\n\n")
        out.write("## Summary\n\n")
        out.write("```log\n")
        if recap:
            out.write(f"{recap}\n")
        else:
            out.write("LOG_RECAP: unavailable\n")

        out.write("TOP_FINDINGS:\n")
        if compact_findings:
            for line in compact_findings:
                out.write(f"{line}\n")
        else:
            out.write("none\n")

        out.write("ACTIONS:\n")
        if actions:
            for idx, action in enumerate(actions, start=1):
                out.write(f"A{idx} | {action}\n")
        else:
            out.write("none\n")
        out.write("```\n")

    logger.info(f"Digest written to {OUTPUT_FILE}")

if __name__ == "__main__":
    format_to_markdown()
