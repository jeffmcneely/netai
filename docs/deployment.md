# netai

## Requirements

- Python 3.11+
- A running [Batfish](https://github.com/batfish/batfish) server
- An S3 bucket for config storage
- OpenAI and/or Anthropic API keys (for ACL features)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` (or just create a `.env`) with:

```
S3_BUCKET=your-bucket-name
BATFISH_SERVER=your-batfish-host
OPENAI_API_KEY=sk-...
CLAUDE_API_KEY=sk-ant-...

# Optional — if configs are stored under an assumed IAM role
AWS_ROLE=arn:aws:iam::123456789012:role/YourRole
AWS_REGION=us-east-1
```

`S3_BUCKET` and `BATFISH_SERVER` are required. The app will refuse to start without them.

## Running

Development:
```bash
python app.py
```

Production-like (gunicorn):
```bash
gunicorn -w 2 -b 0.0.0.0:5000 wsgi:app
```

Docker:
```bash
docker build -t netai:latest .
docker run --env-file .env -p 5000:5000 netai:latest
```

## LLM models

Defaults:
- OpenAI: `gpt-5.4`
- Claude: `claude-sonnet-4-5`

Override via env vars: `OPENAI_MODEL`, `CLAUDE_MODEL`. The ACL optimizer selects Claude automatically when the model string starts with `claude`.
