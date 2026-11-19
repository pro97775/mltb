FROM anasty17/mltb:latest

WORKDIR /app
RUN chmod 777 /app

# Install the latest qBittorrent-nox static build (the Ubuntu PPA lags upstream)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL -o /usr/bin/qbittorrent-nox \
       "https://github.com/userdocs/qbittorrent-nox-static/releases/latest/download/x86_64-qbittorrent-nox" \
    && chmod +x /usr/bin/qbittorrent-nox \
    && rm -rf /var/lib/apt/lists/*

# Smart binary renamer + media-tools symlink directory for yt-dlp compatibility
RUN rename_bin() { \
      src="$(command -v "$1" || command -v "$2" || command -v "$3")" && \
      if [ -n "$src" ] && [ "$src" != "/usr/bin/$3" ]; then mv "$src" "/usr/bin/$3"; fi; \
    } && \
    rename_bin aria2c blitzfetcher "blitzfetcher" && \
    rename_bin qbittorrent-nox stormtorrent "stormtorrent" && \
    rename_bin ffmpeg mediaforge "mediaforge" && \
    rename_bin ffprobe mediaprobe "mediaprobe" && \
    rename_bin rclone ghostdrive "ghostdrive" && \
    rename_bin 7z archiver7 "archiver7" && \
    mkdir -p /opt/media-tools && \
    ln -sf /usr/bin/mediaforge /opt/media-tools/ffmpeg && \
    ln -sf /usr/bin/mediaprobe /opt/media-tools/ffprobe

RUN python3 -m venv appenv

COPY requirements.txt .
RUN appenv/bin/pip install --no-cache-dir -r requirements.txt

COPY . .
RUN sed -i 's/\r$//' *.sh && chmod +x *.sh

CMD ["bash", "start.sh"]
