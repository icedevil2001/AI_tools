#!/usr/bin/env bash
#
# compress-mov.sh - re-encode .mov files in place with ffmpeg
#
# Usage:  ./compress-mov.sh clip.mov
#         ./compress-mov.sh *.mov
#
# Caps the short side at 720px (never upscales), encodes H.264 + AAC,
# and only overwrites the original if the result is actually smaller.

set -euo pipefail

CRF=23          # 18 = near-lossless, 23 = default, 28 = small/lossy
PRESET=medium   # slower = smaller file, same quality
ABITRATE=128k

# Landscape -> cap height at 720. Portrait/square -> cap width at 720.
# -2 keeps the aspect ratio and forces an even dimension (h264 requires it).
SCALE="scale='if(gt(iw,ih),-2,min(720,iw))':'if(gt(iw,ih),min(720,ih),-2)'"

command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg not found in PATH" >&2; exit 1; }

if [ "$#" -eq 0 ]; then
  echo "usage: $(basename "$0") file.mov [file2.mov ...]" >&2
  exit 1
fi

for f in "$@"; do
  if [ ! -f "$f" ]; then
    echo "skip (not a file): $f" >&2
    continue
  fi

  tmp="${f%.*}.tmp.$$.mov"

  echo "==> $f"
  if ! ffmpeg -hide_banner -loglevel error -stats -i "$f" \
      -vf "$SCALE" \
      -c:v libx264 -crf "$CRF" -preset "$PRESET" -pix_fmt yuv420p \
      -c:a aac -b:a "$ABITRATE" \
      -movflags +faststart \
      -y "$tmp"; then
    echo "    encode failed, original untouched" >&2
    rm -f "$tmp"
    continue
  fi

  old=$(wc -c < "$f")
  new=$(wc -c < "$tmp")

  if [ "$new" -ge "$old" ]; then
    echo "    result is not smaller ($new >= $old bytes), keeping original"
    rm -f "$tmp"
    continue
  fi

  touch -r "$f" "$tmp"     # preserve the original timestamp
  mv -f "$tmp" "$f"
  echo "    $((old / 1024 / 1024))MB -> $((new / 1024 / 1024))MB ($((100 - new * 100 / old))% saved)"
done
