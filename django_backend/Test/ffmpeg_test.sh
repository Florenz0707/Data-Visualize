#!/usr/bin/env bash
set -euo pipefail

# ffmpeg test script: per-page slideshow with optional per-page audio naming.
# Naming priority:
# 1) Per-page: speech/s{page}_{idx}.(wav|mp3)
# 2) Fallback: global speech/s{n}.(wav|mp3) sliced by segmented_pages counts
#
# Usage:
#   Test/ffmpeg_test.sh <task_dir> [--fps 24] [--size 1280x720]

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <task_dir> [--fps 24] [--size 1280x720]" >&2
  exit 1
fi

TASK_DIR="$1"; shift || true
FPS=24
SIZE="1280x720"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fps) FPS="${2:-24}"; shift 2;;
    --size) SIZE="${2:-1280x720}"; shift 2;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

IMG_DIR="$TASK_DIR/image"; AUDIO_DIR="$TASK_DIR/speech"; SCRIPT_JSON="$TASK_DIR/script_data.json"
if [[ ! -d "$IMG_DIR" || ! -d "$AUDIO_DIR" || ! -f "$SCRIPT_JSON" ]]; then
  echo "Missing image/, speech/ or script_data.json under $TASK_DIR" >&2; exit 1
fi

WIDTH="${SIZE%x*}"; HEIGHT="${SIZE#*x}"
FFMPEG_BIN="${IMAGEIO_FFMPEG_EXE:-ffmpeg}"; command -v "$FFMPEG_BIN" >/dev/null 2>&1 || { echo "ffmpeg not found" >&2; exit 1; }

# Collect pages images
mapfile -t IMAGES < <(find "$IMG_DIR" -maxdepth 1 -type f \( -iname 'p*.png' -o -iname 'p*.jpg' -o -iname 'p*.jpeg' -o -iname 'p*.webp' \) | sort -V)
[[ ${#IMAGES[@]} -gt 0 ]] || { echo "No page images found" >&2; exit 1; }

# Parse segmented_pages counts (fix here-doc arg order)
readarray -t SEG_COUNTS < <(python - "$SCRIPT_JSON" << 'PY'
import json,sys
if len(sys.argv)<2:
    print('ERR:NO_ARG'); sys.exit(0)
p=sys.argv[1]
try:
    d=json.load(open(p,'r',encoding='utf-8'))
except Exception as e:
    print('ERR:READ_JSON',e); sys.exit(0)
seg=d.get('segmented_pages')
if not isinstance(seg,list):
    pages=d.get('pages',[])
    if isinstance(pages,list):
        tmp=[(pg.get('segments') or []) for pg in pages]
        if any(len(x)>0 for x in tmp): seg=tmp
if not isinstance(seg,list):
    print('ERR:NO_SEG'); sys.exit(0)
for page in seg:
    print(len(page) if isinstance(page,list) else 0)
PY
)
[[ ${#SEG_COUNTS[@]} -gt 0 && "${SEG_COUNTS[0]}" != ERR:* ]] || { printf '%s\n' "${SEG_COUNTS[@]}" >&2; echo "Invalid segmented_pages" >&2; exit 1; }
[[ ${#SEG_COUNTS[@]} -eq ${#IMAGES[@]} ]] || { echo "Mismatch: images=${#IMAGES[@]} vs seg_pages=${#SEG_COUNTS[@]}" >&2; exit 1; }

# Prepare global audios list (sorted numerically by sN)
readarray -t AUDIOS_GLOBAL < <(python - "$AUDIO_DIR" << 'PY'
import os,sys,re
if len(sys.argv)<2:
    sys.exit(0)
adir=sys.argv[1]
try:
    fs=[f for f in os.listdir(adir) if re.match(r"s\d+\.(wav|mp3)$",f,re.I)]
except Exception:
    fs=[]
fs.sort(key=lambda x:int(re.search(r"(\d+)",x).group(1)))
for f in fs: print(os.path.join(adir,f))
PY
)

# Compute required total audios
SUM=0; for c in "${SEG_COUNTS[@]}"; do (( SUM+=c )); done

# Determine mode: enable per-page mode only if every page has exact per-page count
USE_GLOBAL=0
for i in "${!IMAGES[@]}"; do
  page=$((i+1)); need=${SEG_COUNTS[$i]}
  count_page=$(find "$AUDIO_DIR" -maxdepth 1 -type f \( -iname "s${page}_*.wav" -o -iname "s${page}_*.mp3" \) | wc -l | tr -d ' ')
  if [[ "$count_page" -ne "$need" ]]; then
    USE_GLOBAL=1
    break
  fi
done

if [[ $USE_GLOBAL -eq 1 ]]; then
  if [[ ${#AUDIOS_GLOBAL[@]} -ne $SUM ]]; then
    echo "Mismatch: total audio segments found=${#AUDIOS_GLOBAL[@]} but required=$SUM" >&2
    echo "Hint: regenerate Step 4 so that speech files match segmented_pages, or use per-page naming s{page}_{idx}.wav" >&2
    exit 1
  fi
  echo "Mode: global slicing (sN) | Images=${#IMAGES[@]} | RequiredAudios=$SUM"
else
  echo "Mode: per-page naming (s{page}_{idx}) | Images=${#IMAGES[@]}"
fi

WORK_DIR="$(mktemp -d -p "$TASK_DIR" ffmpeg_compose_XXXX)"; trap 'rm -rf "$WORK_DIR"' EXIT
PAGE_VIDS=(); audio_global_cursor=0

for i in "${!IMAGES[@]}"; do
  page=$((i+1)); img="${IMAGES[$i]}"; need=${SEG_COUNTS[$i]}
  aud_list="$WORK_DIR/aud_list_${page}.txt"; : > "$aud_list"
  if [[ $USE_GLOBAL -eq 1 ]]; then
    for ((k=0;k<need;k++)); do printf "file '%s'\n" "${AUDIOS_GLOBAL[$((audio_global_cursor+k))]}" >> "$aud_list"; done
    audio_global_cursor=$((audio_global_cursor+need))
  else
    # per-page: sort s{page}_{idx} by idx (fix here-doc arg order)
    mapfile -t PAGE_AUDS < <(python - "$AUDIO_DIR" "$page" "$need" << 'PY'
import os,sys,re
if len(sys.argv)<4:
    sys.exit(0)
adir=sys.argv[1]; page=sys.argv[2]; need=int(sys.argv[3])
fs=[f for f in os.listdir(adir) if re.match(rf"s{page}_\d+\.(wav|mp3)$", f, re.I)]
fs.sort(key=lambda x:int(re.search(r"_(\d+)", x).group(1)))
print("COUNT", len(fs))
if len(fs)!=need:
    print("ERR", len(fs), need)
else:
    for f in fs: print(os.path.join(adir,f))
PY
)
    if [[ ${#PAGE_AUDS[@]} -gt 0 && "${PAGE_AUDS[0]}" == COUNT* ]]; then
      PAGE_AUDS=("${PAGE_AUDS[@]:1}")
    fi
    if [[ ${#PAGE_AUDS[@]} -ne $need ]]; then
      echo "Page $page per-page files mismatch: found ${#PAGE_AUDS[@]} need $need" >&2
      echo "Debug list (glob s${page}_*.wav|mp3):" >&2
      find "$AUDIO_DIR" -maxdepth 1 -type f \( -iname "s${page}_*.wav" -o -iname "s${page}_*.mp3" \) -printf '%f\n' | sort -V >&2 || true
      exit 1
    fi
    for a in "${PAGE_AUDS[@]}"; do printf "file '%s'\n" "$a" >> "$aud_list"; done
  fi
  merged="$WORK_DIR/merged_${page}.wav"
  "$FFMPEG_BIN" -y -f concat -safe 0 -i "$aud_list" -c:a pcm_s16le "$merged" >/dev/null 2>&1
  page_mp4="$WORK_DIR/page_${page}.mp4"
  "$FFMPEG_BIN" -y -loop 1 -i "$img" -i "$merged" -vf "scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=decrease,pad=${WIDTH}:${HEIGHT}:(ow-iw)/2:(oh-ih)/2:black" \
    -c:v libx264 -tune stillimage -pix_fmt yuv420p -r "$FPS" -c:a aac -shortest "$page_mp4" >/dev/null 2>&1
  PAGE_VIDS+=("$page_mp4")
done

LIST_FILE="$WORK_DIR/list.txt"; : > "$LIST_FILE"
for v in "${PAGE_VIDS[@]}"; do printf "file '%s'\n" "$v" >> "$LIST_FILE"; done
OUT="${TASK_DIR%/}/output.mp4"
"$FFMPEG_BIN" -y -f concat -safe 0 -i "$LIST_FILE" -c copy "$OUT" >/dev/null 2>&1
echo "Done. output: $OUT"