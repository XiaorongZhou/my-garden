# My Garden Agent Handoff

## Project

My Garden is a mobile-first PWA for plant care. Users can:

- keep a per-user garden of plants
- add plants from photos
- run plant diagnoses/check-ins
- ask follow-up questions in a per-plant chat
- log watering with a low-friction daily water button and calendar

The app is intentionally simple and personal. Favor clear, calm mobile UI over feature density.

## Repo And Runtime

- Repo path: `/Users/alicia/Documents/Playground/my-garden`
- Main entrypoint: `app.py`
- Backend package: `my_garden/`
- Frontend app shell: `static/index.html`
- Main frontend controller: `static/app.js`
- Frontend modules: `static/js/`
- Styles: `static/style.css`
- Service worker: `static/sw.js`

Local run:

```bash
cd /Users/alicia/Documents/Playground/my-garden
PORT=8030 python3 -S app.py
```

Default local data paths:

- SQLite DB: `my_garden.db`
- Uploaded images: `uploads/`

Do not commit local data files or uploaded photos.

## Fly.io

Fly app:

- App name: `my-garden`
- URL: `https://my-garden.fly.dev/`
- Region: `sjc`
- Volume: `my_garden_data`
- Volume mount: `/data`
- Production DB: `/data/my_garden.db`
- Production uploads: `/data/uploads`

Deploy:

```bash
cd /Users/alicia/Documents/Playground/my-garden
fly deploy -a my-garden
```

The local data was migrated to Fly on May 9, 2026:

- 17 plants
- 45 check-ins
- 5 watering records
- 4 chat messages
- 25 uploaded files
- 0 missing DB-referenced upload files after verification

If you need to inspect the volume:

```bash
fly ssh console -a my-garden
```

The container does not include the `sqlite3` CLI. Use Python for DB checks:

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("/data/my_garden.db")
print(conn.execute("select count(*) from plants").fetchone()[0])
PY
```

## Auth And Limits

Auth is email + password, with server-issued session tokens.

Important files:

- `my_garden/auth.py`: password hashing and session token helpers
- `my_garden/limits.py`: per-user AI quota enforcement
- `my_garden/data.py`: users, sessions, AI usage, plant/check-in persistence
- `my_garden/server.py`: API routes and auth checks
- `static/js/api.js`: sends `Authorization: Bearer <session_token>`

Passwords are hashed with PBKDF2-SHA256. Session token digests are stored server-side; raw tokens live only in browser local storage.

Existing gardens that predate passwords may set a password on first successful login. Do not reintroduce client-trusted user IDs.

Default AI limits:

- `AI_DAILY_LIMIT=30`
- `AI_IDENTITY_DAILY_LIMIT=10`
- `AI_CHECKIN_DAILY_LIMIT=10`
- `AI_CHAT_DAILY_LIMIT=20`

Fly env config is in `fly.toml`. Model/API secrets must be set through Fly secrets, not committed.

## AI Provider

The app supports OpenAI or an OpenAI-compatible local vision model.

Important files:

- `my_garden/ai_providers.py`
- `my_garden/plant_ai.py`

OpenAI secret is expected as an environment variable or Fly secret. Do not place API keys in source files.

Fly currently may not have an API secret configured. If AI falls back to local guesses on Fly, check:

```bash
fly secrets list -a my-garden
```

Then set secrets if needed:

```bash
fly secrets set -a my-garden OPENAI_API_KEY=... AI_PROVIDER=openai OPENAI_PLANT_MODEL=gpt-5-mini
```

## Frontend Notes

The user cares a lot about demo polish and low-friction mobile UI. Recent direction:

- Do not show the remembered/current garden row on the logged-out login screen.
- Keep the logged-in current garden affordance compact; switching is rarely needed.
- The add plant tab should be photo-first.
- Check-in history should be called "Check-in history", not "Photo history".
- The watering interaction should be a small water icon, not a large CTA.
- Watered days should keep the day number centered; the droplet is a small badge.
- Static generic tips on plant detail were removed; keep tips mostly onboarding/creation-oriented.
- Follow-up chat should be token-efficient and plant-context-specific, not a full ChatGPT clone.

After frontend changes, bump `CACHE_NAME` in `static/sw.js` so the PWA does not serve stale app shell assets.

## Verification

Useful checks:

```bash
cd /Users/alicia/Documents/Playground/my-garden
env PYTHONPYCACHEPREFIX=/private/tmp/my-garden-pycache python3 -m py_compile my_garden/auth.py my_garden/limits.py my_garden/config.py my_garden/data.py my_garden/server.py
node --check static/app.js
node --check static/js/api.js
node --check static/js/views/detail-view.js
```

Local smoke checks:

```bash
curl -s http://127.0.0.1:8030/api/session
curl -s http://127.0.0.1:8030/sw.js
```

Fly smoke check:

```bash
curl -s https://my-garden.fly.dev/api/session
```

Expected unauthenticated auth payload includes:

```json
{"user":null,"session_token":"","claimable_legacy_garden":false}
```

## Git Status Context

As of this handoff, the latest local commit is:

```text
0ef0d89 Add auth, usage limits, and deploy polish
```

It was deployed successfully to Fly, but pushing to GitHub failed because local GitHub auth was not configured for the personal account. The commit author is already:

```text
Alicia Zhou <xz296@cornell.edu>
```

The remote is:

```text
https://github.com/XiaorongZhou/my-garden.git
```

If pushing, use the personal GitHub account for `XiaorongZhou`, not the company/old `aliciaxzhou` auth. A fine-grained PAT needs repository permission `Contents: Read and write` for `XiaorongZhou/my-garden`.

Never commit or expose PATs/API keys.
