# My Garden

Simple local mobile-first web app for plant lovers.

Live app: [https://my-garden.fly.dev](https://my-garden.fly.dev)

It does three things:
- logs the plants you own
- lets you add a photo check-in for any plant
- returns a simple health read and next-step care guidance, with optional text context
- supports either OpenAI or a self-hosted vision-language model for plant identification and diagnosis, with a local heuristic fallback when no live model is available

The seeded demo includes a Maidenhair Fern and a Cat Palm with real photo history so the UI has an immediate story on first launch.

## Run

```bash
cd /Users/alicia/Documents/Playground/my-garden
python3 -S app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

If that port is busy:

```bash
cd /Users/alicia/Documents/Playground/my-garden
PORT=8030 python3 -S app.py
```

Open [http://127.0.0.1:8030](http://127.0.0.1:8030).

## Install On iPhone

My Garden is now packaged as an installable web app (PWA).

To install it on your iPhone:

1. Start the app on your Mac in a way your phone can reach:

```bash
cd /Users/alicia/Documents/Playground/my-garden
HOST=0.0.0.0 PORT=8030 python3 -S app.py
```

2. Find your Mac's local network IP address, then open `http://YOUR_MAC_IP:8030` on your iPhone while both devices are on the same Wi‑Fi network.
3. Prefer HTTPS for the best iPhone web-app support.
4. Open the app in Safari on your iPhone.
5. Tap `Share`.
6. Tap `Add to Home Screen`.

Notes:
- The OpenAI-powered plant ID still runs on the server, so your iPhone needs network access to the machine or host running `app.py`.
- `localhost` or `127.0.0.1` on your Mac will not work from your phone. Use a deployed URL or a hostname/IP your phone can reach.
- A true native iPhone build would still require full Xcode. The current package is an installable standalone web app.

## Deploy On Fly.io

My Garden now includes a basic Fly setup:

- [fly.toml](/Users/alicia/Documents/Playground/my-garden/fly.toml)
- [Dockerfile](/Users/alicia/Documents/Playground/my-garden/Dockerfile)
- [\.dockerignore](/Users/alicia/Documents/Playground/my-garden/.dockerignore)

The Fly config assumes:

- SQLite should live on a persistent volume at `/data/my_garden.db`
- uploaded photos should live at `/data/uploads`
- the app should listen on port `8080`

Typical deploy flow:

```bash
cd /Users/alicia/Documents/Playground/my-garden
flyctl auth login
flyctl apps create my-garden-alicia-zhou
flyctl volumes create my_garden_data --region sjc --size 1
flyctl secrets set OPENAI_API_KEY=your_key_here AI_PROVIDER=openai OPENAI_PLANT_MODEL=gpt-5-mini
flyctl deploy
```

Notes:

- If `my-garden-alicia-zhou` is already taken, update the `app =` value in [fly.toml](/Users/alicia/Documents/Playground/my-garden/fly.toml) and use that name in the `apps create` command.
- If you want a fully self-hosted model path later, you can switch `AI_PROVIDER` away from OpenAI, but the current Fly setup is optimized for the existing OpenAI-backed production flow.
- The persistent volume is important. Without it, your SQLite data and uploaded plant photos would be ephemeral.

## Optional live model

My Garden now has a provider abstraction in [my_garden/ai_providers.py](/Users/alicia/Documents/Playground/my-garden/my_garden/ai_providers.py).

The app-level plant workflows stay the same:
- add plant preview
- existing plant diagnosis
- imported diagnosis compaction

But the runtime provider can now be swapped with environment variables.

### OpenAI mode

If you want the app to use OpenAI for vision and diagnosis:

```bash
cd /Users/alicia/Documents/Playground/my-garden
AI_PROVIDER=openai OPENAI_API_KEY=your_key_here OPENAI_PLANT_MODEL=gpt-5-mini HOST=0.0.0.0 PORT=8030 python3 -S app.py
```

Notes:
- `gpt-5-mini` is the default model if `OPENAI_PLANT_MODEL` is omitted.
- The app falls back to a local backup guess if the key is missing, the model is unavailable, or the image format is unsupported.
- OpenAI vision input supports JPEG, PNG, WEBP, and non-animated GIF image uploads.

### Local model mode

If you want the app to use a self-hosted OpenAI-compatible vision model such as `Qwen/Qwen2.5-VL-7B-Instruct` behind `vLLM`:

```bash
cd /Users/alicia/Documents/Playground/my-garden
AI_PROVIDER=local \
LOCAL_VLM_BASE_URL=http://127.0.0.1:8000/v1 \
LOCAL_VLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct \
HOST=0.0.0.0 PORT=8030 python3 -S app.py
```

Notes:
- `LOCAL_VLM_BASE_URL` should point at an OpenAI-compatible server. `vLLM` is the intended production path.
- `LOCAL_VLM_MODEL` defaults to `Qwen/Qwen2.5-VL-7B-Instruct`.
- `LOCAL_VLM_API_KEY` is optional and only needed if your local gateway requires auth.
- The app still uses the same heuristic fallback if the local model is down or returns invalid output.

## Product shape

- `My plants`: quick list of every plant in your garden
- `Plant detail`: latest diagnosis, next steps, and photo progression
- `New check-in`: one photo plus a short note about what changed

## API

- `GET /api/plants`
- `POST /api/plant-identity-preview`
- `POST /api/plants`
- `GET /api/plants/:id`
- `POST /api/plants/:id/checkins`

`POST /api/plants/:id/checkins` accepts `multipart/form-data`, with:
- `photo`
- `note`

## Files

- `app.py`: server entrypoint
- `my_garden/ai_providers.py`: OpenAI vs local-model provider abstraction
- `my_garden/plant_ai.py`: plant prompts, heuristics, and model-facing workflows
- `my_garden.db`: auto-created SQLite database
- `uploads/`: saved check-in photos
- `static/index.html`: mobile UI
- `static/app.js`: client logic
- `static/style.css`: styling
- `static/manifest.webmanifest`: install metadata for the web app
- `static/sw.js`: service worker for the app shell
- `static/apple-touch-icon.png`, `static/icon-192.png`, `static/icon-512.png`: install icons
