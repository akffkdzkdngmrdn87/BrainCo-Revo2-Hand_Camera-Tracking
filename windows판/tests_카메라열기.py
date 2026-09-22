# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""open_camera 가 「720p 를 못 내는 웹캠」에서도 반드시 열리는지 확인한다.

가짜 cv2 를 끼워 넣어, 윈도우 하드웨어 없이 고장 상황을 재현한다.
"""
import importlib.util
import os
import sys
import types

여기 = os.path.dirname(os.path.abspath(__file__))
본체 = os.path.join(여기, "src", "hand_tracking_control.py")

통과 = 실패 = 0


def 확인(조건, 설명):
    global 통과, 실패
    if 조건:
        통과 += 1; print(f"  \033[32m✓\033[0m {설명}")
    else:
        실패 += 1; print(f"  \033[31m✗\033[0m {설명}")


class 가짜프레임:
    def __init__(self, w, h):
        self.shape = (h, w, 3)


class 가짜캡:
    """웹캠 흉내.

    지원크기  : 이 크기들만 영상을 내준다
    오염      : True 면 지원하지 않는 크기를 요구받은 뒤 영영 망가진다
                (DirectShow 에서 실제로 관찰되는 고장)
    """
    def __init__(self, 지원크기, 오염=False, 열림=True):
        self.지원 = 지원크기
        self.오염될까 = 오염
        self.망가짐 = False
        self.열림 = 열림
        self.크기 = 지원크기[0] if 지원크기 else (640, 480)
        self.닫힘 = False

    def isOpened(self):
        return self.열림

    def set(self, prop, val):
        if prop == 3:                       # CAP_PROP_FRAME_WIDTH
            self.크기 = (int(val), self.크기[1])
        elif prop == 4:                     # CAP_PROP_FRAME_HEIGHT
            self.크기 = (self.크기[0], int(val))
            if self.크기 not in self.지원 and self.오염될까:
                self.망가짐 = True
        return True

    def read(self):
        if self.닫힘 or self.망가짐:
            return False, None
        if self.크기 not in self.지원:
            return False, None
        return True, 가짜프레임(*self.크기)

    def release(self):
        self.닫힘 = True

    def get(self, prop):
        return 0


def 가짜cv2만들기(만들기함수):
    m = types.ModuleType("cv2")
    m.CAP_PROP_FRAME_WIDTH = 3
    m.CAP_PROP_FRAME_HEIGHT = 4
    m.CAP_DSHOW = 700
    m.CAP_MSMF = 1400
    m.CAP_ANY = 0
    m.CAP_V4L2 = 200
    m.VideoCapture = 만들기함수
    return m


def 본체읽기():
    spec = importlib.util.spec_from_file_location("htc_cam", 본체)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = 본체읽기()
mod.IS_WINDOWS = True                       # 윈도우인 척한다 (백엔드 3종)

print("\n1. 640x480 만 되는 웹캠 — 720p 를 요구해도 열려야 한다")
만든것 = []
def 만들기1(idx, be=None):
    c = 가짜캡([(640, 480)], 오염=False); 만든것.append(c); return c
sys.modules["cv2"] = 가짜cv2만들기(만들기1)
cap, 이름, 시도들 = mod.open_camera(0)
확인(cap is not None, f"카메라가 열린다 (백엔드 표시: {이름})")
확인(cap is not None and cap.read()[0], "열린 뒤 실제로 영상이 읽힌다")
확인(이름 is not None and "640x480" in 이름, "640x480 으로 잡힌다")

print("\n2. ★720p 시도 뒤 손잡이가 망가지는 웹캠 (실제 고장 재현)")
def 만들기2(idx, be=None):
    return 가짜캡([(640, 480)], 오염=True)
sys.modules["cv2"] = 가짜cv2만들기(만들기2)
cap, 이름, 시도들 = mod.open_camera(0)
확인(cap is not None, "그래도 카메라가 열린다  ← 이것이 실행 불가의 원인이었다")
확인(cap is not None and cap.read()[0], "열린 뒤 실제로 영상이 읽힌다")
확인(any("되돌림" in t for t in 시도들), f"되돌린 사실을 기록에 남긴다: {시도들[:1]}")

print("\n3. 720p 가 되는 웹캠 — 720p 로 열려야 한다")
def 만들기3(idx, be=None):
    return 가짜캡([(640, 480), (1280, 720)], 오염=False)
sys.modules["cv2"] = 가짜cv2만들기(만들기3)
cap, 이름, 시도들 = mod.open_camera(0)
확인(cap is not None and "1280x720" in (이름 or ""), f"720p 로 열린다 ({이름})")

print("\n4. 정말로 카메라가 없을 때는 정직하게 없다고 해야 한다")
def 만들기4(idx, be=None):
    return 가짜캡([], 열림=False)
sys.modules["cv2"] = 가짜cv2만들기(만들기4)
cap, 이름, 시도들 = mod.open_camera(0)
확인(cap is None, "없으면 None 을 돌려준다")
확인(len(시도들) >= 3, f"백엔드 3종을 모두 시도한 기록이 남는다 ({len(시도들)}건)")

print("\n5. 크기를 직접 지정했을 때")
def 만들기5(idx, be=None):
    return 가짜캡([(640, 480)], 오염=True)
sys.modules["cv2"] = 가짜cv2만들기(만들기5)
cap, 이름, 시도들 = mod.open_camera(0, sizes=[(1920, 1080)])
확인(cap is not None, "지정한 크기가 안 되어도 열린다 (덤은 덤일 뿐)")

print(f"\n결과  통과 {통과}건 · 실패 {실패}건")
sys.exit(1 if 실패 else 0)
