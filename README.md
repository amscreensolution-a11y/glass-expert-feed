# glass-expert-feed

Auto-updated public data feed for **Absolute Mobile Screen / GlassExpert**: a catalog that maps phone models to screen-glass codes. It holds no secrets.

Stable raw URLs (no token needed):

- https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/manifest.json
- https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.json
- https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.sqlite
- https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/glass.py
- https://raw.githubusercontent.com/amscreensolution-a11y/glass-expert-feed/main/APP_API.md

Clients read `manifest.json` (version, sha256, size and url for each file). See [APP_API.md](APP_API.md) for the schema and for Flutter/JS examples. The terminal tool runs `python3 glass.py update`.

A publisher script updates this repo and commits only when the content changes.
