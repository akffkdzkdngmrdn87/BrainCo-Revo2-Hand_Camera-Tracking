#!/usr/bin/env bash
# =============================================================================
#  웹캠 손추적 → BrainCo Revo2 로봇손 실제 구동
#
#  ★ 실행 전 반드시 확인
#     1. 로봇손에 24V DC 어댑터가 꽂혀 있는가
#        (USB 는 통신 전용입니다. 전원이 없으면 포트는 열리지만 응답하지 않습니다)
#     2. USB 케이블이 PC 에 연결되어 있는가
#     3. 로봇손 주변에 손가락이 부딪힐 물건이 없는가
# =============================================================================
set -u
cd "$(dirname "$(readlink -f "$0")")"

CAMERA=0

if [ ! -x .venv/bin/python ]; then
  echo "[안내] 아직 설치되지 않았습니다. 먼저 ./설치.sh 를 실행하십시오."
  read -r; exit 1
fi
if ! ./.venv/bin/python -c "import bc_stark_sdk" 2>/dev/null; then
  echo
  echo "[오류] 제조사 SDK(bc-stark-sdk)가 설치되어 있지 않습니다."
  echo "         ./.venv/bin/pip install bc-stark-sdk"
  echo "         git clone https://github.com/BrainCoTech/brainco-hand-sdk.git ~/brainco-hand-sdk"
  read -r -p "엔터를 누르면 닫힙니다. "; exit 1
fi

echo "=============================================================="
echo " 웹캠 손추적 → 로봇손 실제 구동"
echo "=============================================================="

# ── 1) 로봇이 꽂혀 있는지 ───────────────────────────────────────────────────
if [ ! -e /dev/ttyUSB0 ]; then
  echo
  echo "[오류] /dev/ttyUSB0 이 없습니다. 로봇손 USB 케이블을 확인하십시오."
  echo "       연결하면 아래처럼 잡힙니다:"
  echo "         $ ls /dev/ttyUSB*"
  echo "         /dev/ttyUSB0"
  read -r -p "엔터를 누르면 닫힙니다. "; exit 1
fi
echo "  로봇 포트 : /dev/ttyUSB0  확인"

# 제조사 SDK 는 실행할 때마다 logs/ 에 파일을 남긴다(자동 삭제 안 함).
# 계속 쌓이므로 최근 20개만 남기고 정리한다.
if [ -d logs ]; then
  ls -1t logs/ 2>/dev/null | tail -n +21 | while read -r old; do rm -f "logs/$old"; done
fi


# ── 2) 카메라 ───────────────────────────────────────────────────────────────
./.venv/bin/python src/hand_tracking_control.py --list-cameras || {
  read -r -p "엔터를 누르면 닫힙니다. "; exit 1; }

# ── 3) 포트 권한 ────────────────────────────────────────────────────────────
#   dialout 그룹에 속해야 시리얼 포트를 열 수 있다.
#   그룹에 갓 추가된 경우 재로그인 전까지는 현재 세션에 반영되지 않으므로,
#   sg 로 그룹 권한을 가진 새 셸에서 실행한다.
RUN="./.venv/bin/python src/hand_tracking_control.py --source $CAMERA --backend sdk $*"

if ! id -nG | tr ' ' '\n' | grep -qx dialout; then
  if getent group dialout | grep -qw "$USER"; then
    echo "  포트 권한 : dialout 등록됨(재로그인 전) → sg 로 실행합니다"
    NEEDSG=1
  else
    echo
    echo "[오류] 현재 계정이 dialout 그룹에 없어 시리얼 포트를 열 수 없습니다."
    echo "       아래를 한 번 실행한 뒤 다시 시도하십시오."
    echo "         sudo usermod -aG dialout $USER"
    echo "       (재로그인하면 이후로는 그냥 실행됩니다)"
    read -r -p "엔터를 누르면 닫힙니다. "; exit 1
  fi
else
  echo "  포트 권한 : dialout 확인"
  NEEDSG=0
fi

echo
echo "  창이 열리면 손바닥을 카메라 쪽으로 보여 주십시오."
echo "  조작 : q 종료 | c 가동범위 초기화 | space 일시정지 | o 손 펴기"
echo
echo "  ※ 주먹을 쥐어도 로봇 엄지는 끝까지 닫히지 않습니다."
echo "    접힌 손가락에 막히는 기구적 한계이며 고장이 아닙니다."
echo "=============================================================="
echo

if [ "$NEEDSG" = "1" ]; then
  sg dialout -c "cd '$PWD' && $RUN"
else
  eval "$RUN"
fi

echo
read -r -p "창을 닫으려면 엔터를 누르십시오. "
