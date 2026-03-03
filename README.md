# Multi-Agent Daily Digest (Personal)

Small personal pipeline that turns text notes into a daily markdown digest using 4 Dockerized agents:

1. `ingestor` reads all files from `data/input/`
2. `summarizer` sends combined text to local Ollama
3. `prioritizer` scores lines by urgency keywords
4. `formatter` writes `output/daily_digest.md`

## Requirements

- Linux/WSL/macOS with Docker + Docker Compose
- Ollama installed locally
- A local Ollama model: `llama3:latest`

## Install Ollama

Use the official method for your OS:

- Linux / WSL (Debian/Ubuntu):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

- macOS:
  - Install from: https://ollama.com/download

- Windows:
  - Install from: https://ollama.com/download

After install, start Ollama and pull the model used by this repo:

```bash
ollama serve
ollama pull llama3:latest
ollama list
```

Quick health check:

```bash
curl -s http://127.0.0.1:11434/api/tags
```

## Project Layout

```text
agents/
  ingestor/
  summarizer/
  prioritizer/
  formatter/
data/
  input/               # put your .txt files here
output/
  daily_digest.md      # final result
docker-compose.yml
```

## Quick Start

1. Put your input text files into `data/input/` (for example `notes.txt`, `newsletter.txt`).
2. Run the pipeline:

```bash
docker compose up --build
```

3. Open the result:

```bash
cat output/daily_digest.md
```

## Configuration

Current summarizer settings are in `docker-compose.yml`:

- `OLLAMA_URL=http://127.0.0.1:11434/api/generate`
- `OLLAMA_MODEL=llama3:latest`

If you want a different model, pull it first and then change `OLLAMA_MODEL`.

Note: `.env` includes `OPENAI_API_KEY`, but the current summarizer flow uses Ollama and does not require OpenAI.

## Troubleshooting

### `Ollama error: <urlopen error [Errno 111] Connection refused>`

This means the summarizer container cannot reach Ollama.

Check:

```bash
ollama list
curl -s http://127.0.0.1:11434/api/tags
```

If needed, restart Ollama:

```bash
pkill ollama || true
ollama serve
```

Then rerun:

```bash
docker compose up --build
```

### Permission denied when saving `output/daily_digest.md`

Containers run as UID/GID `1000:1000` in this repo to keep generated files writable in WSL/Linux.
If ownership was broken by older runs:

```bash
chown -R 1000:1000 data output
```

## Optional: Run test

```bash
pytest -q tests/test-prioritizer.py
```
