# Folder 2: Heroku Base / Deploy Repo (Minimal Loader)

Deploy **only** this folder to Heroku. It contains just the minimal bootstrap files so Heroku never scans the full bot codebase during container builds. At startup, `update.py` pulls the full patched bot from your Private Upstream Repo (`3-private-upstream-repo`).

## Included Files
- `Dockerfile` — Minimal container build using your prebuilt base image.
- `heroku.yml` — Heroku Container stack manifest.
- `requirements.txt` — Python dependencies.
- `start.sh` — Activates `appenv`, runs `update.py` to pull `UPSTREAM_REPO`, and starts the worker.
- `services.sh` — Hidden `.svc_rpc.conf` daemon launcher.
- `update.py` — Pulls the full patched code from your private `UPSTREAM_REPO` at runtime.
- `.dockerignore` — Ignores virtual environments and `.git`.
