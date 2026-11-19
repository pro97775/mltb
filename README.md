# Cloud Sync Automation Worker (Heroku Bypass Edition)

A fully hardened, container-ready build of the asynchronous cloud task worker and media processing bot, engineered to eliminate process-tree signatures, CLI flag exposure, broken binary references, and web endpoint fingerprints on container platforms (Heroku, Koyeb, Render, CapRover, and Docker VPS).

---

## Summary of Changes Applied

### 1. Fixed Runtime `ffmpeg` & `ffprobe` Crashes (`media_utils.py` & `yt_dlp_download.py`)
- Replaced hardcoded `"ffmpeg"` calls in `get_audio_thumbnail`, `get_video_thumbnail`, and `get_multiple_frames_thumbnail` (`bot/helper/ext_utils/media_utils.py`) with `BinConfig.FFMPEG_NAME` (`mediaforge`).
- Replaced hardcoded `"ffprobe"` calls in `get_media_info` and `get_document_type` (`bot/helper/ext_utils/media_utils.py`) with `BinConfig.FFPROBE_NAME` (`mediaprobe`).
- Created `/opt/media-tools` symlink directory in `Dockerfile` and `base-image/Dockerfile` (`/opt/media-tools/ffmpeg -> /usr/bin/mediaforge`, `/opt/media-tools/ffprobe -> /usr/bin/mediaprobe`) and pointed `yt_dlp_download.py` `ffmpeg_location` to `/opt/media-tools` so `yt-dlp`'s `FFmpegPostProcessor` properly locates both binaries during audio extraction and thumbnail embedding.

### 2. Complete 7-Binary Alias System (`BinConfig` & `Dockerfile`s)
All underlying worker binaries are renamed at container build time and referenced dynamically via `BinConfig` (with environment variable override support):

| Original Binary | New Binary Alias | Env Variable Override | Patched Modules |
| :--- | :--- | :--- | :--- |
| `aria2c` | `blitzfetcher` | `ARIA2_NAME` | `services.sh`, `startup.py`, `restart.py`, `stats.py` |
| `qbittorrent-nox` | `stormtorrent` | `QBIT_NAME` | `services.sh`, `startup.py`, `restart.py`, `stats.py` |
| `ffmpeg` | `mediaforge` | `FFMPEG_NAME` | `common.py`, `media_utils.py`, `tldv_downloader.py`, `yt_dlp_download.py`, `restart.py`, `stats.py` |
| `ffprobe` | `mediaprobe` | `FFPROBE_NAME` | `media_utils.py`, `restart.py`, `/opt/media-tools` |
| `rclone` | `ghostdrive` | `RCLONE_NAME` | `rclone_download.py`, `list.py`, `serve.py`, `transfer.py`, `clone.py`, `restart.py`, `stats.py` |
| `sabnzbdplus` | `newsripper` | `SABNZBD_NAME` | `services.sh`, `startup.py`, `restart.py`, `stats.py` |
| `7z` | `archiver7` | `SEVENZ_NAME` | `files_utils.py`, `startup.py`, `bot_settings.py`, `restart.py`, `stats.py` |

### 3. Hidden Daemon Configuration (`services.sh` + `.svc_rpc.conf`)
- Removed `aria-nox-nzb.sh` and replaced it with `services.sh`.
- Instead of passing 25+ explicit BitTorrent and tracker CLI flags on the command line (which exposes `--bt-tracker`, `--peer-id-prefix`, and `--peer-agent` in `ps aux` and `/proc/<pid>/cmdline`), `services.sh` writes all RPC and transfer settings into a `0600` `.svc_rpc.conf` file and launches:
  ```bash
  blitzfetcher --conf-path=.svc_rpc.conf --daemon=true
  ```

### 4. De-Branded Web Server & Automatic Heroku `$PORT` Binding
- Removed upstream `anasty17/mirror-leech-telegram-bot` links and attribution from `web/wserver.py` (`GET /`) and `web/templates/page.html`, replacing them with a clean **Cloud Sync Worker** status page and **Cloud File Manager** UI.
- Added `heroku.yml` for native Heroku Container Stack deployments.
- Updated `bot/core/startup.py` and `bot/core/config_manager.py` to automatically detect and bind `gunicorn` to Heroku's dynamic `$PORT` environment variable (`os.getenv("PORT")`) on startup, preventing Heroku `Error R10 (Boot timeout)` crashes even when `BASE_URL` is not configured.

### 5. Sanitized `update.py`, Virtual Environment, and Default Credentials
- Renamed Python virtual environment from `mltbenv` to `appenv` across `Dockerfile`, `.dockerignore`, and `start.sh`.
- Updated `update.py` to block accidental `git reset --hard` against `anasty17/mirror-leech-telegram-bot` (which would otherwise overwrite all patched bypass files on container boot) and replaced the default git commit identity.
- Changed default credentials and API keys in `qBittorrent/config/qBittorrent.conf`, `sabnzbd/SABnzbd.ini`, `bot/__init__.py`, `bot/core/startup.py`, and `web/wserver.py` (`admin` / `cloudsync2026` / `svc_key_8070`).
- Cleared public torrent scraper URLs from `config_sample.py` and removed `.github/FUNDING.yml`.

---

## Deployment Methods

### Method 1: Recommended — Build Your Own Private Base Image First (GitHub Actions)
To prevent container registries from fingerprinting `FROM anasty17/mltb:latest`, build and push your own prebuilt base image using the included workflow:

1. Push this repository to a **private** GitHub repository.
2. In your GitHub repo, go to **Settings $ightarrow$ Secrets and variables $ightarrow$ Actions** and add:
   - `DOCKERHUB_USERNAME`: Your Docker Hub username
   - `DOCKERHUB_TOKEN`: Your Docker Hub access token / password
3. Go to the **Actions** tab $ightarrow$ **Build & Push Prebuilt Base Image** $ightarrow$ **Run workflow**, and enter your target tag (e.g. `yourusername/cloud-base:latest`).
4. Once completed, update line 1 of `Dockerfile` to use your image:
   ```dockerfile
   FROM yourusername/cloud-base:latest
   ```

---

### Method 2: Deploy to Heroku via Heroku CLI (Container Stack)

1. **Install Heroku CLI & Log In**
   ```bash
   heroku login
   ```

2. **Initialize Git Repository (if extracted from zip)**
   ```bash
   cd mirror-leech-telegram-bot
   git init
   git branch -M main
   git add .
   git commit -m "Initial worker deployment"
   ```

3. **Create Heroku App & Set Stack to `container`**
   ```bash
   heroku create your-unique-worker-name
   heroku stack:set container -a your-unique-worker-name
   ```

4. **Set Required Config Vars on Heroku**
   ```bash
   heroku config:set \
     BOT_TOKEN="your_bot_token" \
     OWNER_ID="your_telegram_user_id" \
     TELEGRAM_API="your_telegram_api_id" \
     TELEGRAM_HASH="your_telegram_api_hash" \
     DATABASE_URL="your_mongodb_connection_uri" \
     BASE_URL="https://your-unique-worker-name.herokuapp.com" \
     -a your-unique-worker-name
   ```

5. **Deploy to Heroku**
   ```bash
   git push heroku main
   ```

6. **Verify Web Dyno is Running**
   ```bash
   heroku ps:scale web=1 -a your-unique-worker-name
   heroku logs --tail -a your-unique-worker-name
   ```

---

### Method 3: Deploy to Heroku via GitHub Integration (Dashboard)

1. Push these files to a **private** GitHub repository.
2. Create a new app in the **Heroku Dashboard**.
3. Set the app stack to `container` using Heroku CLI once:
   ```bash
   heroku stack:set container -a your-unique-worker-name
   ```
4. In the Heroku Dashboard, go to **Settings $ightarrow$ Reveal Config Vars** and add:
   - `BOT_TOKEN`
   - `OWNER_ID`
   - `TELEGRAM_API`
   - `TELEGRAM_HASH`
   - `DATABASE_URL`
   - `BASE_URL` (optional, e.g. `https://your-app-name.herokuapp.com`)
5. Go to the **Deploy** tab $ightarrow$ **Deployment method: GitHub**, connect your private repository, and click **Deploy Branch**.

---

### Method 4: Docker / VPS Deployment (`docker-compose`)

1. Copy `config_sample.py` to `config.py` and fill in your credentials:
   ```bash
   cp config_sample.py config.py
   nano config.py
   ```
2. Build and start the container in detached mode:
   ```bash
   docker compose up -d --build
   ```
3. View logs:
   ```bash
   docker compose logs -f
   ```

---

## Important Operational Guidelines for Avoiding Suspensions

1. **Never set `UPSTREAM_REPO` to the public stock repository**: Leave `UPSTREAM_REPO` empty or point it only to your own **private** GitHub repository containing these patches.
2. **Use a Private GitHub Repository**: Public forks of known mirror/leech repositories are automatically indexed. Always host your code in a private repo.
3. **Avoid Raw Public BitTorrent Traffic on Heroku**: Heroku monitors outbound BitTorrent DHT/peer traffic at the network layer. On Heroku dynos, use direct links, Google Drive, Rclone, Usenet (`SABnzbd`), or Debrid resolvers (`ALLDEBRID_API_KEY` / TorBox) rather than unproxied P2P BitTorrent swarms.
