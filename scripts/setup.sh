#!/usr/bin/env bash
# One-time environment setup. Requires: python3 (3.9+), pip, ffmpeg on PATH.
set -e
command -v ffmpeg >/dev/null || { echo "ffmpeg not found (apt install ffmpeg / brew install ffmpeg)"; exit 1; }
python3 -m pip install --quiet numpy pillow
python3 -m pip install --quiet edge-tts || echo "edge-tts optional (voiceover only)"
DIR="$(cd "$(dirname "$0")/.." && pwd)/fonts"; mkdir -p "$DIR"
for f in Montserrat-Black Montserrat-Bold Montserrat-Medium; do
  [ -s "$DIR/$f.ttf" ] || curl -sfL -o "$DIR/$f.ttf" "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/$f.ttf"
done
python3 -c "import numpy, PIL; print('numpy', numpy.__version__, '| pillow', PIL.__version__)"
ffmpeg -version | head -1
echo "setup ok"
