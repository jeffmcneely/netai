# netai

A web front end for [pybatfish](https://github.com/batfish/pybatfish) with some AI hooks for ACL work. You upload network configs to S3, point it at a Batfish server, and get a browser-based interface for analysis and ACL optimization.

## What it does

**Config analysis** (`/analyze`)  
Upload Cisco/NX-OS/ASA configs, run Batfish analysis, and browse results:
- Unreachable ACL rules
- Defined/undefined/unused structures
- Interface inventory
- VLAN table
- SNMP community check
- Explorer (raw Batfish query results)

**ACL optimization** (`/acl-optimize`)  
Paste an ACL, run it through an LLM (OpenAI or Claude), and get back:
- Optimized ACL text
- Verification against original (Batfish-backed)
- CLI commands to deploy the changes
- "Remove junk" — async job that strips redundant/shadowed entries

**Search**  
Search configs for IP addresses or string patterns across all uploaded files.

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

## Project structure

```
app/
  routes/       # ui.py (page routes), api.py (JSON endpoints)
  services/     # batfish_manager, s3_manager, openai_manager, claude_manager, ip_finder, filename_manager
  templates/    # Jinja2 HTML
  static/       # CSS and vanilla JS
  utils/        # validators, response helpers
app.py          # dev entrypoint
wsgi.py         # production entrypoint
```
