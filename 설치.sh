#!/usr/bin/env bash
# =============================================================================
#  BrainCo Revo2 카메라 손추적 — 설치
#  가상환경을 이 폴더 안에만 만듭니다. 시스템 파이썬과 ~/.local 을 건드리지 않습니다.
#  여러 번 실행해도 안전합니다(이미 있으면 다시 받지 않습니다).
# =============================================================================
set -u
cd "$(dirname "$(readlink -f "$0")")"
echo "=============================================================="
echo " BrainCo Revo2 카메라 손추적 — 설치"
echo "=============================================================="

command -v python3 >/dev/null || { echo "[오류] python3 가 없습니다.  sudo apt install python3 python3-venv"; exit 1; }
echo "[1/5] python3 : $(python3 --version)"

if [ ! -x .venv/bin/python ]; then
  echo "[2/5] 가상환경을 만듭니다 (.venv)"
  python3 -m venv .venv || { echo "[오류] python3-venv 가 필요합니다: sudo apt install python3-venv"; exit 1; }
else
  echo "[2/5] 가상환경 이미 있음"
fi

if ./.venv/bin/python -c "import mediapipe, cv2" 2>/dev/null; then
  echo "[3/5] mediapipe·opencv 이미 설치됨"
else
  echo "[3/5] mediapipe·opencv 를 내려받습니다 (약 200MB, 몇 분 걸립니다)"
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install opencv-python mediapipe || { echo "[오류] 설치 실패"; exit 1; }
fi

MODEL=models/hand_landmarker.task
if [ -s "$MODEL" ]; then
  echo "[4/5] 손 랜드마크 모델 이미 있음 ($(du -h "$MODEL" | cut -f1))"
else
  echo "[4/5] 손 랜드마크 모델을 내려받습니다 (7.8MB)"
  mkdir -p models
  curl -L --fail -o "$MODEL" \
    https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task \
    || { echo "[오류] 모델 내려받기 실패. 인터넷 연결을 확인하십시오."; exit 1; }
fi

# ── 로봇을 쓸 것인지 물어본다 (선택) ───────────────────────────────────────
echo "[5/5] 로봇 제어 준비 (선택)"
if ./.venv/bin/python -c "import bc_stark_sdk" 2>/dev/null; then
  echo "      bc-stark-sdk 이미 설치됨"
else
  echo "      로봇을 실제로 움직이려면 제조사 SDK 가 필요합니다(MIT)."
  read -r -p "      지금 설치할까요? [y/N] " a
  if [[ "${a:-N}" =~ ^[Yy] ]]; then
    ./.venv/bin/pip install bc-stark-sdk || echo "      [경고] bc-stark-sdk 설치 실패"
    [ -d "$HOME/brainco-hand-sdk/python/revo2" ] \
      || git clone --depth 1 https://github.com/BrainCoTech/brainco-hand-sdk.git "$HOME/brainco-hand-sdk" \
      || echo "      [경고] SDK 예제 clone 실패"
  else
    echo "      건너뜁니다. 나중에:  ./.venv/bin/pip install bc-stark-sdk"
  fi
fi
if ! id -nG | tr ' ' '\n' | grep -qx dialout; then
  echo
  echo "      ※ 현재 계정이 dialout 그룹에 없습니다. 로봇을 쓰려면 필요합니다."
  echo "        sudo usermod -aG dialout $USER      (다음 로그인부터 적용)"
fi

echo
echo "=============================================================="
echo " 설치 완료. 자체 검증을 실행합니다."
echo "=============================================================="
./.venv/bin/python src/hand_tracking_control.py --self-test
echo
echo "카메라 목록:"
./.venv/bin/python src/hand_tracking_control.py --list-cameras
echo
echo "다음 단계"
echo "  로봇 없이 화면만 :  ./실행_웹캠.sh"
echo "  로봇 실제 구동   :  ./실행_웹캠_로봇.sh"
