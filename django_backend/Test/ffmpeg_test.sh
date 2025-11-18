#!/usr/bin/env bash
set -euo pipefail

# Generic ffmpeg test script for per-page slideshow composition.
# - One image per page (image/pN.{png,jpg,jpeg,webp})
# - Multiple short audios per sentence (speech/sK.{wav,mp3})
# - segmented_pages in script_data.json determines how many audio segments belong to each page
#
# Usage:
#   Test/ffmpeg_test.sh <task_dir> [--fps 24] [--size 1280x720]
# Example:
#   Test/ffmpeg_test.sh generated_stories/1 --fps 24 --size 1280x720

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <task_dir> [--fps 24] [--size 1280x720]" >&2
  exit 1
fi

TASK_DIR="$1"; shift || true
FPS=24
SIZE="1280x720"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fps)
      FPS="${2:-24}"; shift 2;;
    --size)
      SIZE="${2:-1280x720}"; shift 2;;
    *)
      echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

if [[ ! -d "$TASK_DIR" ]]; then
  echo "Task dir not found: $TASK_DIR" >&2; exit 1
fi
IMG_DIR="$TASK_DIR/image"
AUDIO_DIR="$TASK_DIR/speech"
SCRIPT_JSON="$TASK_DIR/script_data.json"
if [[ ! -d "$IMG_DIR" || ! -d "$AUDIO_DIR" || ! -f "$SCRIPT_JSON" ]]; then
  echo "Missing required directories/files under $TASK_DIR (need image/, speech/, script_data.json)" >&2
  exit 1
fi

# Parse width/height
WIDTH="${SIZE%x*}"
HEIGHT="${SIZE#*x}"

FFMPEG_BIN="${IMAGEIO_FFMPEG_EXE:-ffmpeg}"
if ! command -v "$FFMPEG_BIN" >/dev/null 2>&1; then
  echo "ffmpeg not found in PATH and IMAGEIO_FFMPEG_EXE not set." >&2
  exit 1
fi

# Collect image files (sorted by name) - support common extensions
mapfile -t IMAGES < <(find "$IMG_DIR" -maxdepth 1 -type f \( \
  -iname 'p*.png' -o -iname 'p*.jpg' -o -iname 'p*.jpeg' -o -iname 'p*.webp' \) \
  | sort -V)
if [[ ${#IMAGES[@]} -eq 0 ]]; then
  echo "No page images found under $IMG_DIR" >&2; exit 1
fi

# Collect audio files (sorted by name)
mapfile -t AUDIOS < <(find "$AUDIO_DIR" -maxdepth 1 -type f \( -iname 's*.wav' -o -iname 's*.mp3' \) | sort -V)
if [[ ${#AUDIOS[@]} -eq 0 ]]; then
  echo "No audio segment files found under $AUDIO_DIR" >&2; exit 1
fi

# Read segmented_pages counts via Python to avoid jq dependency
readarray -t SEG_COUNTS < <(python - << 'PY'
import json,sys,os
p=sys.argv[1]
with open(p,'r',encoding='utf-8') as f:
    data=json.load(f)
seg_pages=None
if isinstance(data,dict):
    seg_pages=data.get('segmented_pages')
elif isinstance(data,list):
    seg_pages=data
if not isinstance(seg_pages,list):
    print('ERR:NO_SEG_PAGES',flush=True)
    sys.exit(0)
for page in seg_pages:
    if isinstance(page,list):
        print(len(page))
    else:
        print(0)
PY
"$SCRIPT_JSON")

if [[ ${#SEG_COUNTS[@]} -eq 0 || "${SEG_COUNTS[0]}" == ERR:NO_SEG_PAGES ]]; then
  echo "segmented_pages missing or invalid in $SCRIPT_JSON" >&2
  exit 1
fi

# Validate counts vs images and audios
if [[ ${#SEG_COUNTS[@]} -ne ${#IMAGES[@]} ]]; then
  echo "Mismatch: pages(images)=${#IMAGES[@]} but segmented_pages=${#SEG_COUNTS[@]}" >&2
  exit 1
fi
SUM=0; for c in "${SEG_COUNTS[@]}"; do (( SUM+=c )); done
if [[ $SUM -ne ${#AUDIOS[@]} ]]; then
  echo "Mismatch: total audio segments=${#AUDIOS[@]} but required by segmented_pages=$SUM" >&2
  exit 1
fi

echo "Images: ${#IMAGES[@]} | Audios: ${#AUDIOS[@]} | FPS=$FPS | SIZE=${WIDTH}x${HEIGHT}"

WORK_DIR="$(mktemp -d -p "$TASK_DIR" ffmpeg_compose_XXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

audio_idx=0
PAGE_VIDS=()
for i in "${!IMAGES[@]}"; do
  page=$((i+1))
  img="${IMAGES[$i]}"
  need=${SEG_COUNTS[$i]}

  # Build concat list for this page
  aud_list="$WORK_DIR/aud_list_${page}.txt"
  : > "$aud_list"
  for ((k=0;k<need;k++)); do
    a="${AUDIOS[$((audio_idx+k))]}"
    # use POSIX path
    a_posix="$(echo "$a" | sed 's~\\\\~\/~g')"
    printf "file '%s'\n" "$a_posix" >> "$aud_list"
  done
  audio_idx=$((audio_idx+need))

  merged="$WORK_DIR/merged_${page}.wav"
  echo "[Page $page] concat audio -> $merged"
  "$FFMPEG_BIN" -y -f concat -safe 0 -i "$aud_list" -c:a pcm_s16le "$merged" >/dev/null 2>&1

  page_mp4="$WORK_DIR/page_${page}.mp4"
  echo "[Page $page] build video -> $page_mp4 (image=$(basename "$img"), size=${WIDTH}x${HEIGHT}, fps=$FPS)"
  "$FFMPEG_BIN" -y \
    -loop 1 -i "$img" -i "$merged" \
    -vf "scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=decrease,pad=${WIDTH}:${HEIGHT}:(ow-iw)/2:(oh-ih)/2:black" \
    -c:v libx264 -tune stillimage -pix_fmt yuv420p -r "$FPS" \
    -c:a aac -shortest "$page_mp4" >/dev/null 2>&1
  PAGE_VIDS+=("$page_mp4")

done

# Concat pages
LIST_FILE="$WORK_DIR/list.txt"
: > "$LIST_FILE"
for v in "${PAGE_VIDS[@]}"; do
  v_posix="$(echo "$v" | sed 's~\\\\~\/~g')"
  printf "file '%s'\n" "$v_posix" >> "$LIST_FILE"
done
OUT="${TASK_DIR%/}/output.mp4"
echo "[Final] concat ${#PAGE_VIDS[@]} pages -> $OUT"
"$FFMPEG_BIN" -y -f concat -safe 0 -i "$LIST_FILE" -c copy "$OUT" >/dev/null 2>&1

echo "Done. output: $OUT"

