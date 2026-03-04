import logging
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("summarizer")

INPUT_FILE = "/data/ingested.txt"
OUTPUT_FILE = "/data/summary.txt"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")
OLLAMA_TIMEOUT_SEC = int(os.getenv("OLLAMA_TIMEOUT_SEC", "300"))
ENABLE_PREDICTION = os.getenv("ENABLE_PREDICTION", "true").lower() in {
    "1", "true", "yes", "on"
}
MAX_MODEL_INPUT_CHARS = int(os.getenv("MAX_MODEL_INPUT_CHARS", "120000"))
MAX_SIGNAL_LINES = int(os.getenv("MAX_SIGNAL_LINES", "4000"))
MAX_TAIL_LINES = int(os.getenv("MAX_TAIL_LINES", "300"))
MAX_OUTPUT_LINES = int(os.getenv("MAX_OUTPUT_LINES", "120"))
MIN_VALID_SUMMARY_LINES = int(os.getenv("MIN_VALID_SUMMARY_LINES", "3"))
MAX_FINDINGS = int(os.getenv("MAX_FINDINGS", "5"))
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    (
        "You analyze large log batches and detect operational issues. "
        "Return plain text lines only (not markdown bullets). "
        "Do not add intro sentences, markdown headings, or paragraphs. "
        "Always start with one recap line in this exact format: "
        "'LOG_RECAP: ...'. "
        "Then list findings as one line per issue in this exact format: "
        "'FINDING: severity=Critical|High|Medium|Low | source=... | "
        "error=... | impact=... | action=... | evidence=...'. "
        "Prioritize failures, exceptions, and recurring warnings. "
        "If no errors are found, include "
        "'NO_ERRORS: none detected' and 'ACTION: continue monitoring'. "
        "Keep each line short, specific, and factual. "
        "Do not use unicode bullets such as '•'."
    ),
)
PREDICTIVE_PROMPT = os.getenv(
    "PREDICTIVE_PROMPT",
    (
        "If input includes tabular or time-series patterns, add forecast bullets "
        "in this format: '- Prediction: ...', '- Confidence: ...', "
        "'- Rationale: ...'. "
        "If data is not sufficient, include "
        "'- Prediction: Not reliable (insufficient data)'."
    ),
)

FILE_MARKER_RE = re.compile(r"^---\s+(.+?)\s+---\s*$")
SERVICE_RE = re.compile(r"\bservice=([A-Za-z0-9._:-]+)")
MESSAGE_RE = re.compile(r'msg="([^"]+)"')
SIGNAL_TOKENS = (
    "level=critical",
    "[critical]",
    "level=error",
    "[error]",
    "exception",
    "traceback",
    "fatal",
    "build failure",
    "failed to execute",
    "cannot find symbol",
    "timeout",
    "level=warn",
    "[warn]",
    "[warning]",
    " warning",
)
SEVERITY_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


def is_signal_line(line):
    lower = line.lower()
    return any(token in lower for token in SIGNAL_TOKENS)


def condense_input_for_model(text):
    if len(text) <= MAX_MODEL_INPUT_CHARS:
        return text, False

    lines = text.splitlines()
    signal_lines = []
    current_marker = None
    last_marker_written = None

    for raw_line in lines:
        line = raw_line.rstrip()
        marker = FILE_MARKER_RE.match(line.strip())
        if marker:
            current_marker = marker.group(1)
            continue

        if not is_signal_line(line):
            continue

        if current_marker and last_marker_written != current_marker:
            signal_lines.append(f"--- {current_marker} ---")
            last_marker_written = current_marker

        signal_lines.append(line)
        if len(signal_lines) >= MAX_SIGNAL_LINES:
            break

    tail_lines = lines[-MAX_TAIL_LINES:]
    condensed_lines = [
        (
            "[Input condensed for model: "
            f"original_chars={len(text)} original_lines={len(lines)}]"
        ),
        "[Signal-focused excerpt]",
    ]
    if signal_lines:
        condensed_lines.extend(signal_lines)
    else:
        condensed_lines.append(
            "No explicit signal lines found. Using recent tail excerpt."
        )

    condensed_lines.append("[Recent tail excerpt]")
    condensed_lines.extend(tail_lines)

    condensed = "\n".join(condensed_lines)
    if len(condensed) > MAX_MODEL_INPUT_CHARS:
        condensed = condensed[:MAX_MODEL_INPUT_CHARS]
    return condensed, True


def build_prompt(text):
    prompt = SYSTEM_PROMPT
    if ENABLE_PREDICTION:
        prompt = f"{prompt}\n\n{PREDICTIVE_PROMPT}"
    return f"{prompt}\n\nInput:\n{text}"


def normalize_summary_lines(summary):
    normalized = []
    seen = set()

    for raw_line in summary.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("- "):
            content = stripped[2:].strip()
        elif stripped.startswith("* "):
            content = stripped[2:].strip()
        elif stripped.startswith("•"):
            content = stripped.lstrip("•").strip()
        else:
            content = stripped

        if not content:
            continue

        lower = content.lower()
        if lower.startswith("here is the daily digest"):
            continue
        if lower.startswith("here are the plain text lines"):
            continue

        if content.lower() in seen:
            continue
        seen.add(content.lower())
        normalized.append(content)

    if len(normalized) > MAX_OUTPUT_LINES:
        normalized = normalized[:MAX_OUTPUT_LINES]
    return normalized


def summary_is_usable(lines):
    if len(lines) < MIN_VALID_SUMMARY_LINES:
        return False
    if not lines[0].lower().startswith("log_recap:"):
        return False

    has_structured_findings = any(
        line.lower().startswith("finding:")
        or line.lower().startswith("no_errors:")
        or line.lower().startswith("action:")
        for line in lines[1:]
    )
    if not has_structured_findings:
        return False

    meaningful = 0
    total_len = 0
    for line in lines:
        total_len += len(line)
        if re.search(r"[A-Za-z0-9]{3}", line):
            meaningful += 1

    avg_len = total_len / len(lines) if lines else 0
    if meaningful < MIN_VALID_SUMMARY_LINES:
        return False
    if avg_len < 8:
        return False
    return True


def extract_message(line):
    message = MESSAGE_RE.search(line)
    if message:
        return message.group(1).strip()[:180]

    cleaned = re.sub(r"^\d{4}-\d{2}-\d{2}T\S+\s*", "", line)
    cleaned = re.sub(r"\bservice=\S+\s*", "", cleaned)
    cleaned = re.sub(r"\blevel=\S+\s*", "", cleaned)
    cleaned = re.sub(r"\breq_id=\S+\s*", "", cleaned)
    cleaned = re.sub(
        r"^\[(INFO|WARN|WARNING|ERROR|CRITICAL)\]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:180]


def detect_severity(line_lower):
    if "critical" in line_lower:
        return "Critical"
    if (
        "error" in line_lower
        or "exception" in line_lower
        or "traceback" in line_lower
        or "fatal" in line_lower
        or "fail" in line_lower
        or "timeout" in line_lower
    ):
        return "High"
    if "warn" in line_lower or "warning" in line_lower:
        return "Medium"
    return "Low"


def scan_logs(text):
    level_counts = Counter({"INFO": 0, "WARN": 0, "ERROR": 0, "CRITICAL": 0})
    events = {}
    current_source = "unknown"
    sources = set()
    total_lines = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        marker = FILE_MARKER_RE.match(line)
        if marker:
            current_source = marker.group(1)
            sources.add(current_source)
            continue

        total_lines += 1
        lower = line.lower()

        if "level=info" in lower or line.startswith("[INFO]"):
            level_counts["INFO"] += 1
        if (
            "level=warn" in lower
            or line.startswith("[WARN]")
            or line.startswith("[WARNING]")
        ):
            level_counts["WARN"] += 1
        if "level=error" in lower or line.startswith("[ERROR]"):
            level_counts["ERROR"] += 1
        if "level=critical" in lower or line.startswith("[CRITICAL]"):
            level_counts["CRITICAL"] += 1

        if not is_signal_line(line):
            continue

        source_match = SERVICE_RE.search(line)
        source = source_match.group(1) if source_match else current_source
        message = extract_message(line)
        severity = detect_severity(lower)
        key = (severity, source, message)
        if key not in events:
            events[key] = {"count": 0, "evidence": line}
        events[key]["count"] += 1

    sorted_events = sorted(
        events.items(),
        key=lambda item: (SEVERITY_RANK.get(item[0][0], 0), item[1]["count"]),
        reverse=True,
    )

    return {
        "total_lines": total_lines,
        "source_count": len(sources) or 1,
        "level_counts": level_counts,
        "events": sorted_events,
    }


def build_recap_line(scan):
    counts = scan["level_counts"]
    return (
        "LOG_RECAP: scanned "
        f"{scan['total_lines']} lines across {scan['source_count']} file(s); "
        f"critical={counts['CRITICAL']}, error={counts['ERROR']}, "
        f"warn={counts['WARN']}, info={counts['INFO']}."
    )


def impact_text(severity):
    if severity == "Critical":
        return "Potential outage or major transaction loss risk."
    if severity == "High":
        return "Failed operations likely affecting users."
    if severity == "Medium":
        return "Early warning signs that can become incidents."
    return "Low immediate impact."


def action_text(severity, source):
    if severity in {"Critical", "High"}:
        return f"Investigate {source} immediately and verify recovery."
    if severity == "Medium":
        return f"Review {source} warnings and set alert thresholds."
    return f"Monitor {source} for recurrence."


def build_fallback_summary(text):
    scan = scan_logs(text)
    lines = [build_recap_line(scan)]

    if not scan["events"]:
        lines.append("NO_ERRORS: none detected")
        lines.append("ACTION: continue monitoring")
        return "\n".join(lines)

    for (severity, source, message), meta in scan["events"][:MAX_FINDINGS]:
        lines.append(
            "FINDING: "
            f"severity={severity} | "
            f"source={source} | "
            f"error={message} (x{meta['count']}) | "
            f"impact={impact_text(severity)} | "
            f"action={action_text(severity, source)} | "
            f"evidence={meta['evidence'][:220]}"
        )

    return "\n".join(lines)


def finalize_summary(model_summary, raw_text):
    normalized = normalize_summary_lines(model_summary)
    if summary_is_usable(normalized):
        if not normalized[0].lower().startswith("log_recap:"):
            normalized.insert(0, build_recap_line(scan_logs(raw_text)))
        return "\n".join(normalized[:MAX_OUTPUT_LINES])

    logger.warning(
        "Model summary failed quality checks; using deterministic fallback."
    )
    return build_fallback_summary(raw_text)


def summarize_locally(text):
    """Call a local Ollama instance from inside a Docker container."""
    condensed_text, was_condensed = condense_input_for_model(text)
    if was_condensed:
        logger.info(
            "Condensed input for model: original=%d chars, sent=%d chars",
            len(text),
            len(condensed_text),
        )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": build_prompt(condensed_text),
        "stream": False
    }
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=OLLAMA_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
            content = resp.read().decode("utf-8")
        return json.loads(content).get("response", "No response")
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as e:
        return f"Ollama error: {e}"

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read()

    if not raw_text.strip():
        logger.warning("Empty input. Writing fallback summary.")
        summary = "LOG_RECAP: no input data available.\nNO_ERRORS: none detected"
    else:
        try:
            model_summary = summarize_locally(raw_text)
            if model_summary.startswith("Ollama error:"):
                logger.error(model_summary)
                summary = build_fallback_summary(raw_text)
            else:
                summary = finalize_summary(model_summary, raw_text)
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            summary = build_fallback_summary(raw_text)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(summary)
    logger.info(f"Summary written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
