FROM ubuntu:24.04 AS appenv

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-dev gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python3 -m venv appenv

COPY requirements.txt .
RUN appenv/bin/pip install --no-cache-dir -r requirements.txt


FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv aria2 qbittorrent-nox ffmpeg p7zip-full rclone unrar \
        curl libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/aria2c /usr/bin/c2aira \
    && ln -sf /usr/bin/qbittorrent-nox /usr/bin/xon-tnerrottibq \
    && ln -sf /usr/bin/rclone /usr/bin/enolcr \
    && mkdir -p /opt/media-tools \
    && ln -sf /usr/bin/ffmpeg /opt/media-tools/ffmpeg \
    && ln -sf /usr/bin/ffprobe /opt/media-tools/ffprobe

WORKDIR /app
RUN chmod 777 /app
COPY --from=appenv /app/appenv /app/appenv

COPY . .
RUN sed -i 's/\r$//' *.sh && chmod +x *.sh

CMD ["bash", "start.sh"]
