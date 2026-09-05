#!/usr/bin/env bash
# =============================================================================
#  시연 자료 3종을 한 번에 다시 만든다 (WebP / MP4 / 썸네일)
#  사용법:  bash media/다시만들기.sh <원본영상.mp4>
#
#  GitHub 한도를 넘지 않도록 크기를 확인하고, 넘으면 자동으로 더 줄인다.
# =============================================================================
set -u
cd "$(dirname "$(readlink -f "$0")")"
SRC="${1:-}"
[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "사용법: bash media/다시만들기.sh <원본영상.mp4>"; exit 1; }
command -v ffmpeg >/dev/null || { echo "[오류] ffmpeg 가 필요합니다: sudo apt install ffmpeg"; exit 1; }

LIMIT=$((10 * 1024 * 1024))     # GitHub 무료 첨부 한도 10MB

echo "[1/3] MP4 (H.264 · faststart · 무음)"
ffmpeg -v error -y -i "$SRC" -c:v libx264 -profile:v high -pix_fmt yuv420p \
  -b:v 1450k -maxrate 1800k -bufsize 3000k -preset slow -movflags +faststart -an \
  손추적_시연.mp4
echo "      $(du -h 손추적_시연.mp4 | cut -f1)"

echo "[2/3] 애니메이션 WebP (대문 자동 재생용) — 한도 안에 들 때까지 조정"
# 화질이 좋은 설정부터 시도하고, 10MB 를 넘으면 한 단계씩 낮춘다.
for cfg in "12:640:38" "10:600:34" "10:560:32" "10:520:30" "8:520:30"; do
  IFS=: read -r fps w q <<< "$cfg"
  ffmpeg -v error -y -i "$SRC" -vf "fps=$fps,scale=$w:-2" -c:v libwebp \
    -lossless 0 -q:v "$q" -loop 0 -preset picture -an -vsync 0 손추적_시연.webp
  SZ=$(stat -c%s 손추적_시연.webp)
  printf "      fps=%-3s 폭=%-4s q=%-3s → %5.1f MB" "$fps" "$w" "$q" "$(awk -v s=$SZ 'BEGIN{print s/1048576}')"
  if [ "$SZ" -lt "$LIMIT" ]; then echo "  ✔ 채택"; break; else echo "  ✘ 한도 초과, 다음 설정"; fi
done

echo "[3/3] 썸네일"
ffmpeg -v error -y -ss 20 -i "$SRC" -frames:v 1 -vf "scale=406:-2" 손추적_시연_썸네일.jpg
echo "      $(du -h 손추적_시연_썸네일.jpg | cut -f1)"

echo
echo "완료:"
ls -lh 손추적_시연.webp 손추적_시연.mp4 손추적_시연_썸네일.jpg | awk '{printf "  %-28s %s\n", $9, $5}'
