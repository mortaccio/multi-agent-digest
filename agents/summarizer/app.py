import logging
import json
import os
import urllib.error
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("summarizer")

INPUT_FILE = "/data/ingested.txt"
OUTPUT_FILE = "/data/summary.txt"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")

def summarize_locally(text):
    """Call a local Ollama instance from inside a Docker container."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": (
            "Summarize the following text into key "
            f"bullet points:\n\n{text}"
        ),
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
        with urllib.request.urlopen(req, timeout=120) as resp:
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
        summary = "No content to summarize."
    else:
        try:
            summary = summarize_locally(raw_text)
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            summary = f"Summarization failed: {e}"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(summary)
    logger.info(f"Summary written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
