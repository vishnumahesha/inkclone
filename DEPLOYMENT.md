# InkClone Deployment

## Live URL

**https://inkclone-pro.fly.dev/**

Deployed on [Fly.io](https://fly.io) via Docker container.

## Infrastructure

| Setting | Value |
|---------|-------|
| Platform | Fly.io |
| App name | inkclone-pro |
| Region | Dallas, Texas (US) |
| Machine | shared-cpu-1x, 1GB RAM |
| Port | 8000 (internal) → 443 HTTPS (public) |
| Container | python:3.11-slim + tesseract-ocr |

## Deployment Commands

```bash
# Build locally
docker build -t inkclone .
docker run -p 8001:8000 inkclone

# Deploy to Fly.io
fly deploy
```

## Verify

```bash
curl -s -o /dev/null -w "%{http_code}" https://inkclone-pro.fly.dev/
# → 200
```

## Notes

- Auto-stop/start enabled (machine sleeps when idle, wakes on first request)
- HTTPS enforced via Fly.io proxy
- Cloudflare quick-tunnel (`trycloudflare.com`) was unavailable at deploy time due to network-level connection resets from this host
