#!/bin/bash
set -e

# ==============================================================================
# Prebuilt Base Image Builder & Pusher (Single-Layer Squashed Image)
# Usage:
#   chmod +x build-base-image.sh
#   ./build-base-image.sh yourdockerhubusername/cloud-base:latest
# ==============================================================================

IMAGE_TAG="${1:-yourusername/cloud-base:latest}"

ARIA2_NAME="${ARIA2_NAME:-blitzfetcher}"
QBIT_NAME="${QBIT_NAME:-stormtorrent}"
FFMPEG_NAME="${FFMPEG_NAME:-mediaforge}"
FFPROBE_NAME="${FFPROBE_NAME:-mediaprobe}"
RCLONE_NAME="${RCLONE_NAME:-ghostdrive}"
SABNZBD_NAME="${SABNZBD_NAME:-newsripper}"
SEVENZ_NAME="${SEVENZ_NAME:-archiver7}"

echo "============================================================"
echo " Building squashed base image: $IMAGE_TAG"
echo "============================================================"
echo " ARIA2_NAME   = $ARIA2_NAME"
echo " QBIT_NAME    = $QBIT_NAME"
echo " FFMPEG_NAME  = $FFMPEG_NAME"
echo " FFPROBE_NAME = $FFPROBE_NAME"
echo " RCLONE_NAME  = $RCLONE_NAME"
echo " SABNZBD_NAME = $SABNZBD_NAME"
echo " SEVENZ_NAME  = $SEVENZ_NAME"
echo "============================================================"

docker build \
  -f base-image/Dockerfile \
  --build-arg ARIA2_NAME="$ARIA2_NAME" \
  --build-arg QBIT_NAME="$QBIT_NAME" \
  --build-arg FFMPEG_NAME="$FFMPEG_NAME" \
  --build-arg FFPROBE_NAME="$FFPROBE_NAME" \
  --build-arg RCLONE_NAME="$RCLONE_NAME" \
  --build-arg SABNZBD_NAME="$SABNZBD_NAME" \
  --build-arg SEVENZ_NAME="$SEVENZ_NAME" \
  -t "$IMAGE_TAG" .

echo ""
echo "[+] Build complete! Pushing $IMAGE_TAG to Docker Hub..."
docker push "$IMAGE_TAG"

# Automatically update Dockerfile FROM line if Dockerfile exists
if [ -f "Dockerfile" ]; then
  sed -i "s|^FROM .*|FROM ${IMAGE_TAG}|" Dockerfile
  echo "[+] Updated Dockerfile to use: FROM $IMAGE_TAG"
fi

echo ""
echo "[✓] Done! Your custom prebuilt base image is live at: $IMAGE_TAG"
