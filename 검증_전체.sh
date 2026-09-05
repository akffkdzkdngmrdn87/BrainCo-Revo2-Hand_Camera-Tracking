#!/usr/bin/env bash
# =============================================================================
#  전체 검증 — 장비가 없어도 끝까지 돌아갑니다.
#    1) 계산 논리 자체시험      2) 제스처 의미 검증(사진 자동 내려받기)
#    3) 영상 처리               4) 카메라 목록
#    5) 로봇 실기 구동시험      ← 로봇이 없으면 건너뜁니다
# =============================================================================
set -u
cd "$(dirname "$(readlink -f "$0")")"
[ -x .venv/bin/python ] || { echo "먼저 ./설치.sh 를 실행하십시오."; read -r; exit 1; }
P=./.venv/bin/python
mkdir -p 결과
LOG="결과/검증실행_$(date +%Y%m%d_%H%M%S).log"

# 제조사 SDK 는 실행 때마다 logs/ 에 파일을 남긴다. 최근 20개만 남긴다.
if [ -d logs ]; then
  ls -1t logs/ 2>/dev/null | tail -n +21 | while read -r old; do rm -f "logs/$old"; done
fi

{
  echo "검증 실행 : $(date '+%Y-%m-%d %H:%M:%S')"
  echo "장비      : $(uname -srm)"
  $P -c "import mediapipe,cv2,sys;print('환경      : python',sys.version.split()[0],'| mediapipe',mediapipe.__version__,'| opencv',cv2.__version__)"
  echo
  echo "##### 1. 계산 논리 자체시험 #####"
  $P src/hand_tracking_control.py --self-test
  echo
  echo "##### 2. 제스처 의미 검증 #####"
  $P tests/제스처_검증.py
  echo
  echo "##### 3. 영상 처리 #####"
  # ★ 반드시 주석이 없는 원본 영상을 넣어야 한다.
  #   시연용 media/손추적_시연.mp4 는 이미 골격선과 수치가 그려져 있어서,
  #   그것을 다시 입력으로 넣으면 그림이 손을 가려 검출률이 2%대로 떨어진다.
  if [ -f media/시험입력_짧은판.mp4 ]; then
    $P src/hand_tracking_control.py --source media/시험입력_짧은판.mp4 \
        --backend none --headless --csv 결과/검증_영상.csv
  else
    echo "  media/시험입력_짧은판.mp4 이 없습니다. 건너뜁니다."
  fi
  echo
  echo "##### 4. 카메라 목록 #####"
  $P src/hand_tracking_control.py --list-cameras
  echo
  echo "##### 5. 로봇 실기 구동 시험 #####"
  if [ ! -e /dev/ttyUSB0 ]; then
    echo "  로봇이 연결되어 있지 않습니다(/dev/ttyUSB0 없음). 건너뜁니다."
    echo "  → USB 케이블과 24V DC 어댑터를 연결한 뒤 다시 실행하십시오."
  elif ! $P -c "import bc_stark_sdk" 2>/dev/null; then
    echo "  bc-stark-sdk 가 설치되어 있지 않습니다. 건너뜁니다."
    echo "  → ./.venv/bin/pip install bc-stark-sdk"
  elif [ ! -d "$HOME/brainco-hand-sdk/python/revo2" ]; then
    echo "  제조사 SDK 예제가 없습니다. 건너뜁니다."
    echo "  → git clone https://github.com/BrainCoTech/brainco-hand-sdk.git ~/brainco-hand-sdk"
  else
    if id -nG | tr " " "\n" | grep -qx dialout; then
      $P tests/실기_구동시험.py 2>&1 | grep -v -E "^2026-|INFO\]"
    else
      sg dialout -c "cd '$PWD' && $P tests/실기_구동시험.py" 2>&1 | grep -v -E "^2026-|INFO\]"
    fi
  fi
} 2>&1 | grep -v -E "^(INFO:|WARNING: Logging|W0000)" | tee "$LOG"

echo
echo "기록을 남겼습니다: $LOG"
read -r -p "창을 닫으려면 엔터를 누르십시오. "
