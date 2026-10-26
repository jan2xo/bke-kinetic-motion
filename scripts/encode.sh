#!/usr/bin/env bash
# encode.sh <frames_dir> <audio.wav|none> <out.mp4> <duration_s> [fps=30] [lufs=-16]
set -e
FR="$1"; AU="$2"; OUT="$3"; DUR="$4"; FPS="${5:-30}"; LUFS="${6:--16}"
TMP="$(mktemp -d)/out.mp4"   # write locally first: network filesystems can break the faststart trailer rewrite
if [ "$AU" = "none" ]; then
  ffmpeg -y -v error -framerate "$FPS" -i "$FR/f%04d.png" -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -t "$DUR" -movflags +faststart "$TMP"
else
  ffmpeg -y -v error -framerate "$FPS" -i "$FR/f%04d.png" -i "$AU" \
    -filter_complex "[1:a]loudnorm=I=${LUFS}:TP=-1.5:LRA=11,atrim=0:${DUR}[a]" -map 0:v -map "[a]" \
    -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -c:a aac -b:a 192k -t "$DUR" -movflags +faststart "$TMP"
fi
cp "$TMP" "$OUT"; echo "wrote $OUT"
