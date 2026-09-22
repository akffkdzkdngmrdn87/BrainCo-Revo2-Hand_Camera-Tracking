#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""화면 표시(전체 화면·해상도·창) 시험대.

왜 필요한가
    2026-09-10 에 전체 화면 기능을 넣으면서 `list_cameras()` 안에
    **정의되지 않은 변수**(cam_sizes)를 남겨 `--list-cameras` 가 죽었다.
    화면 관련 코드는 창을 띄워야 확인되는 줄 알기 쉽지만,
    이런 결함은 창 없이도 잡을 수 있다. 그래서 시험대로 고정한다.

실행
    ../.venv/bin/python 시험_화면표시.py
"""
import importlib.util
import os
import subprocess
import sys

여기 = os.path.dirname(os.path.abspath(__file__))
본체 = os.path.join(여기, "src", "hand_tracking_control.py")

통과 = 0
실패 = 0


def 확인(조건, 설명):
    """조건이 참이면 통과로 센다."""
    global 통과, 실패
    if 조건:
        통과 += 1
        print(f"  \033[32m✓\033[0m {설명}")
    else:
        실패 += 1
        print(f"  \033[31m✗\033[0m {설명}")


def 본체읽기():
    """본체를 모듈로 읽어 온다(실행은 하지 않는다)."""
    spec = importlib.util.spec_from_file_location("htc", 본체)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


m = 본체읽기()

print("\n1. 전체 화면 장치가 갖춰져 있는가")
확인(hasattr(m, "WIN_NAME"), "창 이름이 상수로 정해져 있다")
확인("f" in getattr(m, "WIN_NAME", ""), "창 제목에 f 키 안내가 들어 있다")
확인(callable(getattr(m, "set_fullscreen", None)), "전체 화면 전환 함수가 있다")

print("\n2. 해상도 후보가 전체 화면에 맞는가")
크기들 = getattr(m, "CAM_SIZES", [])
확인(크기들 and 크기들[0] == (1280, 720), "720p 를 먼저 요청한다 (전체 화면에서 안 흐리도록)")
확인((640, 480) in 크기들, "안 되면 640x480 으로 내려간다")

print("\n3. 창이 없어도 죽지 않는가")
try:
    m.set_fullscreen("존재하지_않는_창", True)
    m.set_fullscreen("존재하지_않는_창", False)
    확인(True, "없는 창에 걸어도 예외가 새지 않는다")
except Exception as e:                                  # noqa: BLE001
    확인(False, f"예외가 샜다: {e}")

print("\n4. 사람이 고를 수 있는가")
p = m.build_parser()
확인(not p.parse_args(["--source", "0"]).windowed, "기본은 전체 화면이다")
확인(p.parse_args(["--source", "0", "--windowed"]).windowed, "--windowed 로 창 모드를 고른다")
확인(p.parse_args(["--source", "0", "--cam-size", "640x480"]).cam_size == "640x480",
     "--cam-size 로 해상도를 지정한다")

print("\n5. 이름이 정의되기 전에 쓰이는 곳이 없는가")
# ★ 이것이 2026-09-10 결함을 잡은 항목이다.
#   화면 없이(headless) 실제로 돌려서 NameError 를 잡는다.
환경 = dict(os.environ)
환경.pop("DISPLAY", None)
환경["OPENCV_VIDEOIO_PRIORITY_V4L2"] = "0"
결과 = subprocess.run([sys.executable, 본체, "--list-cameras"],
                     capture_output=True, text=True, timeout=120, env=환경)
확인("NameError" not in 결과.stderr, "--list-cameras 에 NameError 가 없다")
확인("Traceback" not in 결과.stderr, "--list-cameras 가 예외로 죽지 않는다")
# 종료코드 1 은 「웹캠이 하나도 없다」는 정상 결과다(이 PC 가 그렇다).
# 2 이상이나 음수만 비정상으로 본다.
확인(결과.returncode in (0, 1), f"--list-cameras 종료코드가 정상 범위다 ({결과.returncode})")

결과2 = subprocess.run([sys.executable, 본체, "--list-ports"],
                      capture_output=True, text=True, timeout=120, env=환경)
확인("NameError" not in 결과2.stderr, "--list-ports 에 NameError 가 없다")

print(f"\n결과  통과 {통과}건 · 실패 {실패}건")
if 실패:
    print("\033[31m실패가 있습니다.\033[0m")
    sys.exit(1)
print("\033[32m모두 통과했습니다.\033[0m")
