# Copilot Instructions for netai

## Project Overview
- This repository is a Flask web app for network config upload, Batfish analysis, ACL optimization, and search utilities.
- Backend code lives under `app/` with modular services and route blueprints.
- UI is server-rendered Jinja templates plus vanilla JavaScript and CSS under `app/templates` and `app/static`.

## Runtime and Entry Points
- Local development entrypoint: `app.py`.
- Production WSGI entrypoint: `wsgi.py`.
- Flask app factory: `app.create_app()` in `app/__init__.py`.
- Docker runtime command uses gunicorn: `gunicorn -w 2 -b 0.0.0.0:5000 wsgi:app`.

## Required Environment and Startup Behavior
- App startup must fail fast if either `S3_BUCKET` or `BATFISH_SERVER` is missing/blank.
- If `AWS_ROLE` is configured, startup must validate role assumption at boot (`bootstrap_assumed_role`).
- Keep config parsing in `app/config.py` with safe defaults and `.strip()` for string env vars.
- Keep existing default model behavior unless explicitly requested:
  - OpenAI default: `gpt-5.4`
  - Claude default: `claude-sonnet-4-5`

## Architecture and Module Boundaries
- Routes:
  - `app/routes/ui.py`: template routes only.
  - `app/routes/api.py`: JSON APIs and orchestration.
- Services:
  - `batfish_manager.py`: Batfish snapshot/query logic and serialization.
  - `s3_manager.py`: S3 folder/file operations and role-refresh-aware clients.
  - `openai_manager.py`, `claude_manager.py`: LLM calls for ACL optimize/commands.
  - `ip_finder.py`, `filename_manager.py`: focused pure utility services.
- Utilities:
  - `app/utils/validators.py`: request/input validation and parsing.
  - `app/utils/responses.py`: standardized API response envelope.

## API Response Contract
- Use shared response helpers from `app/utils/responses.py`:
  - `ok(data, status=...)`
  - `fail(message, code, status=..., field=...)`
- Keep response shape stable:
  - success: `status=success`, `timestamp`, `data`
  - error: `status=error`, `timestamp`, `error.code`, `error.message` (+ optional field)
- Preserve existing error code strings unless there is a clear reason to introduce a new one.

## Validation and Input Rules
- Reuse existing validators in `app/utils/validators.py`; do not duplicate ad hoc parsing in routes.
- Treat form/query booleans explicitly (for example, `1/true/yes/on`). Do not use naive `bool(string)` parsing for flags.
- Always sanitize user-provided filenames via `sanitize_filename` before S3/file access.
- Keep folder names constrained to current rules (`validate_folder_name`) and reject path traversal patterns.

## Route Implementation Patterns
- For API endpoints, follow this exception order:
  1. `ValidationError` -> `400` with `VALIDATION_ERROR`
  2. Known timeout/domain exceptions where applicable (for example LLM timeout -> `504`)
  3. Catch-all `Exception` -> endpoint-specific `..._ERROR` with `500`
- Keep routes thin: parse/validate inputs, call managers, transform for response only.
- Prefer helper functions in `api.py` for repeated logic (`_resolve_config_folder`, `_normalize_search_filters`, etc.).

## S3 and AWS Role Handling
- `S3Manager` supports optional role assumption with STS.
- Preserve credential refresh behavior with a pre-expiration window (5 minutes) in `_credentials_expiring_soon`.
- Avoid creating alternate boto3 client flows outside `S3Manager`.

## Batfish Integration Rules
- Keep Batfish session initialization lazy in `BatfishManager._session()`.
- Continue using `_frame_to_records` and `_serialize_value` to ensure JSON-safe response payloads.
- Snapshot naming can remain dynamic, but avoid collisions and preserve current snapshot workflow.

## LLM Manager Rules
- Keep OpenAI and Claude managers structurally aligned:
  - Similar timeout handling and explicit timeout exception mapping.
  - Return non-empty output text or raise a clear error.
- Do not silently swallow LLM exceptions.
- Preserve explicit model selection behavior in `_acl_llm_manager` (Claude chosen when model string starts with `claude`).

## Frontend Conventions
- Keep HTML IDs stable; `app/static/js/app.js` is heavily ID-driven.
- Prefer enhancing existing sections/components over introducing frameworks.
- Keep styling in `app/static/css/main.css` and preserve existing visual language unless asked for redesign.
- Maintain accessibility basics already present (button types, aria labels, roles).

## Dependency and Version Guidance
- Python dependencies are pinned in `requirements.txt`.
- Use currently listed libraries and avoid introducing new dependencies unless necessary.
- If adding a dependency, update `requirements.txt` and ensure Docker build still works.

## Coding Style
- Follow existing Python style:
  - type hints where practical
  - small helper functions for normalization/parsing
  - clear error messages intended for API clients
- Keep logging/debug patterns consistent with existing modules.
- Keep changes focused; avoid unrelated refactors.

## Verification Checklist for Changes
- For backend changes:
  - app imports cleanly and app factory still builds
  - key API routes return standardized response envelopes
  - validation failures produce `VALIDATION_ERROR` and proper HTTP status
- For AWS/S3 changes:
  - role-assumption path and non-role path both remain valid
- For frontend changes:
  - affected pages load: `/`, `/analyze`, `/acl-optimize`
  - corresponding JS interactions still bind by existing IDs
- For container changes:
  - `docker build -t netai:latest .` succeeds

## Suggested Local Run Commands
- Activate venv: `source .venv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Run app (dev): `python app.py`
- Run app (prod-like): `gunicorn -w 2 -b 0.0.0.0:5000 wsgi:app`

## Non-Goals Unless Requested
- Do not redesign API schema.
- Do not rename route paths or response fields.
- Do not replace vanilla JS UI with another frontend framework.
- Do not loosen input validation constraints around folder names, filenames, ports, or IPs.
