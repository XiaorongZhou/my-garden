# My Garden

Simple local mobile-first web app for plant lovers.

It does three things:
- logs the plants you own
- lets you add a photo check-in for any plant
- returns a simple health read and next-step care guidance, with optional text context
- uses a live vision model for plant identification when `OPENAI_API_KEY` is available, with a local fallback guess when it is not

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

## Optional live plant ID

If you want the add flow to identify plants from the uploaded photo with a real model, run the server with:

```bash
cd /Users/alicia/Documents/Playground/my-garden
OPENAI_API_KEY=your_key_here OPENAI_PLANT_MODEL=gpt-5-mini HOST=0.0.0.0 PORT=8030 python3 -S app.py
```

Notes:
- `gpt-5-mini` is the default model if `OPENAI_PLANT_MODEL` is omitted.
- The app falls back to a local backup guess if the key is missing, the model is unavailable, or the image format is unsupported.
- OpenAI vision input supports JPEG, PNG, WEBP, and non-animated GIF image uploads.

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

- `app.py`: server, API, SQLite persistence, OpenAI-backed plant ID, diagnosis heuristics
- `my_garden.db`: auto-created SQLite database
- `uploads/`: saved check-in photos
- `static/index.html`: mobile UI
- `static/app.js`: client logic
- `static/style.css`: styling
- `static/manifest.webmanifest`: install metadata for the web app
- `static/sw.js`: service worker for the app shell
- `static/apple-touch-icon.png`, `static/icon-192.png`, `static/icon-512.png`: install icons
