#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 pi2jw
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# BrainCo, Revo2 는 BrainCo, Inc. 의 상표입니다. 본 파일은 제조사의 공식
# 소프트웨어가 아니며, 호환 대상 하드웨어를 지칭하기 위해서만 상표를 사용합니다.
"""
================================================================================
 BrainCo Revo2 Basic 로봇손 — 카메라 손추적 추종 제어  (전면 재작성판)
================================================================================

■ 이 파일이 하는 일
   웹캠(또는 영상파일)에 비친 "사람 손"의 관절을 구글 MediaPipe 로 추정하고,
   손가락이 얼마나 굽었는지를 0~1000 숫자 6개로 바꾸어
   BrainCo Revo2 로봇손이 그대로 따라 하도록 명령을 보냅니다.

■ 왜 다시 만들었는가 (구판 hand_tracking_control.py 의 결함)
   ① 구판은 `mediapipe.solutions.hands` 를 씁니다. 이 레거시 API 는
      2023-03-01 자로 지원이 끝났고, 현행 mediapipe 1.x 에서는 모듈 자체가
      삭제되어 실행 즉시 AttributeError 로 죽습니다.
      → 현행 표준인 MediaPipe **Tasks API** (HandLandmarker) 로 교체했습니다.
   ② 구판의 손가락 배열이 [엄지, 검지, 중지, 약지, 소지, 손목] 로 틀렸습니다.
      실제 확정값은 [엄지, 엄지보조, 검지, 중지, 약지, 소지] 입니다.
      (같은 저장소 hand_keyboard.py 및 제3자 구현 szwedk/brainco-revo2-hand-control
       의 engine/protocol.py 가 독립적으로 일치)
      → 구판대로 두면 "검지를 굽혔는데 엄지가 돌아가는" 오동작이 납니다.
   ③ 구판의 굽힘 계산은 (1.5 - 손끝거리/뿌리거리) * 1000 같은 임의 상수 식이라
      손 크기와 카메라 거리에 따라 결과가 달라집니다.
      → 크기와 무관한 **관절 각도** 방식으로 교체했습니다.
   ④ 구판은 cv2.putText 로 한글을 그립니다. OpenCV 기본 폰트는 ASCII 전용이라
      화면에 ??? 로 깨집니다. → Pillow 로 한글을 그리도록 바꿨습니다.
   ⑤ 구판은 로봇과 ROS 2 가 둘 다 있어야만 실행됩니다. → 아무것도 없이도
      돌려볼 수 있는 모의(mock) 출력을 기본값으로 두어 검증이 가능해졌습니다.

■ 손가락 배열 (전 저장소 공통 규약)
      인덱스: [ 0     1        2     3     4     5   ]
      손가락: [ 엄지  엄지보조  검지  중지  약지  소지 ]
      값    :   0 = 완전히 폄  ~  1000 = 완전히 쥠
      ※ '엄지보조'는 엄지를 손바닥 쪽으로 돌리는(대립/회전) 축입니다.
        사람 손에는 대응하는 "굽힘"이 없으므로, 엄지 중수골이 검지 중수골과
        벌어진 각도(벌림각)로 환산합니다. 손을 쫙 펴면 벌어지고(0),
        주먹을 쥐면 손바닥 쪽으로 붙습니다(1000).

■ 출력 방식 3가지 (--backend)
      none  : 아무 장비 없이 화면·기록만 (기본값, 검증용)
      ros2  : 경로 B. /set_motor_multi_127 토픽으로 SetMotorMulti 발행
              (별도 터미널에서 stark 컨트롤러 노드가 떠 있어야 함)
      sdk   : 경로 A. bc_stark_sdk 로 /dev/ttyUSB0 직접 제어 (ROS 2 불필요)
      ※ ros2 와 sdk 는 같은 시리얼 포트를 두고 다투므로 동시 사용 금지.

■ 입력 방식 3가지 (--source)
      0, 1, 2 ...      : 웹캠 장치 번호
      파일.mp4         : 영상 파일 (카메라가 없어도 검증 가능)
      사진.jpg         : 정지 이미지 1장

■ 실행 예
      python3 hand_tracking_control.py                      # 웹캠 0번, 모의출력
      python3 hand_tracking_control.py --backend sdk        # 로봇 직접 제어
      python3 hand_tracking_control.py --backend ros2       # ROS 2 경유
      python3 hand_tracking_control.py --source demo.mp4 --headless \
              --record 결과/주석영상.mp4 --csv 결과/기록.csv
      python3 hand_tracking_control.py --self-test          # 장비 없이 논리 검증

■ 안전 규칙 (저장소 전체 공통)
      시작할 때와 끝날 때 반드시 손을 활짝 폅니다(전부 0).
      손을 놓치면 마지막 자세를 유지하다가, 일정 시간이 지나면 스스로 폅니다.
================================================================================
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import queue
import sys
import threading
import time

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# 상수 정의
# ─────────────────────────────────────────────────────────────────────────────

FINGER_NAMES = ["엄지", "엄지보조", "검지", "중지", "약지", "소지"]
FINGER_NAMES_EN = ["Thumb", "ThumbRot", "Index", "Middle", "Ring", "Pinky"]
N_FINGER = 6
POS_OPEN, POS_CLOSED = 0, 1000      # 0 = 완전히 폄, 1000 = 완전히 쥠

# MediaPipe 손 랜드마크 21점의 인덱스 (공식 정의)
#   0  손목
#   1~4   엄지  : CMC(뿌리) MCP IP TIP(끝)
#   5~8   검지  : MCP PIP DIP TIP
#   9~12  중지  : MCP PIP DIP TIP
#   13~16 약지  : MCP PIP DIP TIP
#   17~20 소지  : MCP PIP DIP TIP
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP = 5
PINKY_MCP = 17

# 네 손가락(검지·중지·약지·소지)의 관절 인덱스 (MCP, PIP, DIP, TIP)
FOUR_FINGER_JOINTS = {
    "검지": (5, 6, 7, 8),
    "중지": (9, 10, 11, 12),
    "약지": (13, 14, 15, 16),
    "소지": (17, 18, 19, 20),
}

# ─────────────────────────────────────────────────────────────────────────────
# 계산 축(axis) — 로봇의 6칸과 1:1 이 아니다
#   카메라에서 직접 잴 수 있는 것은 아래 여섯 가지다.
#   이것을 조합해서 로봇 배열 6칸(FINGER_NAMES)을 만든다.
#     엄지굽힘 : 엄지 관절이 굽은 정도
#     엄지벌림 : 엄지가 손바닥 쪽으로 모였는가(대립/내전)
# ─────────────────────────────────────────────────────────────────────────────
AXIS_NAMES = ["엄지굽힘", "엄지벌림", "검지", "중지", "약지", "소지"]
AXIS_NAMES_EN = ["ThumbFlex", "ThumbAbd", "Index", "Middle", "Ring", "Pinky"]

# 각도 → 0~1000 변환의 초기 기준값 (단위: 도).  '폄' 쪽 각도가 크고 '쥠' 쪽이 작다.
#
# ★ 이 숫자들은 짐작이 아니라 실측값이다.
#   위키미디어 공용의 손동작 사진 6장(손펴기·주먹·브이·엄지척·OK)과
#   저장소 시연영상 897프레임에서 각 축의 각도 분포를 뽑아 정했다.
#   측정 기록: 결과/각도분포_실측.txt
#     네 손가락 : 편 손 171~178도,  주먹 91~95도
#     엄지굽힘  : 편 손 173도,      접은 엄지 113도   ← 가동폭이 좁다
#     엄지벌림  : 벌린 엄지 165도,  모은 엄지 54도
CAL_DEFAULT = {
    #             폄(=0)   쥠(=1000)
    "엄지굽힘":  (175.0, 110.0),
    "엄지벌림":  (166.0,  50.0),
    "검지":      (179.0,  91.0),
    "중지":      (179.0,  91.0),
    "약지":      (179.0,  91.0),
    "소지":      (179.0,  91.0),
}

# 로봇의 '엄지' 칸을 만들 때 굽힘과 벌림을 섞는 비율.
#   사람이 주먹을 쥘 때 엄지는 '굽는다'기보다 '손바닥 쪽으로 모인다'.
#   굽힘만 쓰면 주먹인데도 엄지 값이 낮게 나와 로봇 주먹이 헐거워진다.
#   실측에서 굽힘 단독은 주먹 474, 섞으면 616 으로 개선되었다.
THUMB_BLEND = 0.55          # 엄지 = 0.55*굽힘 + 0.45*벌림

# 화면에 그릴 손 골격 연결선 (MediaPipe HAND_CONNECTIONS 와 동일)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),           # 엄지
    (0, 5), (5, 6), (6, 7), (7, 8),           # 검지
    (5, 9), (9, 10), (10, 11), (11, 12),      # 중지
    (9, 13), (13, 14), (14, 15), (15, 16),    # 약지
    (13, 17), (17, 18), (18, 19), (19, 20),   # 소지
    (0, 17),                                  # 손바닥 아래변
]

# 한글을 그릴 폰트 후보 (앞에서부터 있는 것을 사용)
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # 최후: 한글 안 나옴
]

# 모델 파일을 찾을 위치 (앞에서부터)
_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_CANDIDATES = [
    os.environ.get("HAND_LANDMARKER_MODEL", ""),
    os.path.join(_HERE, "..", "models", "hand_landmarker.task"),
    os.path.join(_HERE, "models", "hand_landmarker.task"),
    os.path.expanduser("~/.cache/mediapipe/hand_landmarker.task"),
]
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")


# ─────────────────────────────────────────────────────────────────────────────
# 기하 계산 — 여기가 이 프로그램의 핵심 논리
# ─────────────────────────────────────────────────────────────────────────────

def angle_at(b, a, c) -> float:
    """
    점 b 를 꼭짓점으로 하는 각 ∠(a-b-c) 를 '도(degree)' 단위로 돌려준다.

    왜 각도인가:
      손 크기가 크든 작든, 카메라에서 멀든 가깝든 관절이 굽은 '각도'는 같다.
      구판이 쓰던 거리 비율은 이 성질이 없어서 사람마다 값이 달라졌다.

    계산 방법 (고등학교 벡터 내적):
      v1 = a - b,  v2 = c - b  두 벡터를 만들고
      cosθ = (v1·v2) / (|v1||v2|)  →  θ = arccos(cosθ)
    """
    v1 = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    v2 = np.asarray(c, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-9 or n2 < 1e-9:          # 점이 겹치면 각을 정의할 수 없다
        return float("nan")
    # 부동소수 오차로 |cos| 가 1을 아주 살짝 넘으면 arccos 가 NaN 을 낸다 → 잘라둔다
    cos = float(np.dot(v1, v2) / (n1 * n2))
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))


def angle_between(v1, v2) -> float:
    """두 '방향벡터' 사이의 각(도). 관절이 아니라 뼈의 방향을 비교할 때 쓴다."""
    v1 = np.asarray(v1, dtype=np.float64)
    v2 = np.asarray(v2, dtype=np.float64)
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return float("nan")
    cos = max(-1.0, min(1.0, float(np.dot(v1, v2) / (n1 * n2))))
    return math.degrees(math.acos(cos))


def landmarks_to_array(landmarks, use_z: bool) -> np.ndarray:
    """
    MediaPipe 랜드마크 목록을 (21, 3) 넘파이 배열로 바꾼다.

    use_z=False 이면 z 를 0 으로 눌러 '평면(2D) 각도'를 쓴다.
      MediaPipe 의 z 는 손등이 카메라를 향할 때 불안정하다고 보고되어 있다
      (google-ai-edge/mediapipe 이슈 #4931). 손바닥을 카메라로 향하는
      통상적인 사용에서는 2D 가 오히려 안정적인 경우가 많다.
    """
    arr = np.array([[p.x, p.y, (p.z if use_z else 0.0)] for p in landmarks],
                   dtype=np.float64)
    return arr


def compute_raw_angles(pts: np.ndarray) -> dict:
    """
    21점 좌표에서 손가락 6축의 '원시 각도'(도)를 뽑는다.
    이 각도는 아직 0~1000 이 아니다. 보정(Calibrator)을 거쳐야 위치값이 된다.

    반환: {"엄지":각도, "엄지보조":각도, "검지":…, "중지":…, "약지":…, "소지":…}
          각도가 크다 = 폈다,  작다 = 굽혔다  (여섯 축 모두 방향이 같다)
    """
    out = {}

    # ── 네 손가락: MCP·PIP·DIP 세 관절 각의 가중평균 ───────────────────────
    #    PIP(둘째 마디)가 굽힘을 가장 잘 나타내므로 가장 크게 반영한다.
    for name, (mcp, pip, dip, tip) in FOUR_FINGER_JOINTS.items():
        a_mcp = angle_at(pts[mcp], pts[WRIST], pts[pip])   # 손목–MCP–PIP
        a_pip = angle_at(pts[pip], pts[mcp],  pts[dip])    # MCP–PIP–DIP
        a_dip = angle_at(pts[dip], pts[pip],  pts[tip])    # PIP–DIP–TIP
        vals, wts = [], []
        for v, w in ((a_mcp, 0.30), (a_pip, 0.45), (a_dip, 0.25)):
            if not math.isnan(v):
                vals.append(v); wts.append(w)
        out[name] = float(np.average(vals, weights=wts)) if vals else float("nan")

    # ── 엄지굽힘: MCP·IP 두 관절 각의 평균 ───────────────────────────────
    #    엄지는 관절이 하나 적고 가동범위도 좁아서 따로 처리한다.
    a1 = angle_at(pts[THUMB_MCP], pts[THUMB_CMC], pts[THUMB_IP])
    a2 = angle_at(pts[THUMB_IP],  pts[THUMB_MCP], pts[THUMB_TIP])
    vals = [v for v in (a1, a2) if not math.isnan(v)]
    out["엄지굽힘"] = float(np.mean(vals)) if vals else float("nan")

    # ── 엄지벌림: 엄지가 가리키는 방향과 손등 MCP 줄이 이루는 각 ──────────
    #    MCP 줄(검지뿌리 → 소지뿌리)은 손등에 고정된 기준선이다.
    #      엄지를 옆으로 쫙 벌림 → 각 큼(약 165도)  → 위치값 0
    #      엄지를 손바닥에 모음 → 각 작음(약 52도)  → 위치값 1000
    #
    #    ※ 후보 5가지를 실사진으로 실측 비교해 이 식을 골랐다
    #      (프리셋 대비 평균오차 167 로 최저). 비교 기록: 결과/엄지축_산출식_비교.txt
    out["엄지벌림"] = angle_between(pts[THUMB_TIP] - pts[THUMB_MCP],
                                    pts[PINKY_MCP] - pts[INDEX_MCP])

    return out


class Calibrator:
    """
    각도(도) → 위치값(0~1000) 변환기.

    동작 원리:
      각 축마다 '폄 기준각(open)'과 '쥠 기준각(close)'을 갖고 선형 보간한다.
          위치 = (open - 현재각) / (open - close) * 1000
      기준각은 CAL_DEFAULT 의 실측 표준값으로 시작하되,
      그보다 더 큰/작은 각이 실제로 관측되면 **기준을 넓히기만** 한다.

      ※ 왜 좁히지는 않는가
        좁히기(자동 축소)를 넣으면, 손을 가만히 두었을 때 기준폭이 계속
        오그라들어 미세한 떨림이 0~1000 전체로 증폭된다. 실제로 이 현상을
        확인했기에 '넓히기 전용'으로 고정했다.
        기준을 다시 잡고 싶으면 실행 중 c 키를 누른다.
    """

    def __init__(self, adaptive: bool = True, margin: float = 1.0):
        self.adaptive = adaptive
        self.margin = margin          # 관측값을 넘어설 때 더해줄 여유(도)
        self.reset()

    def reset(self):
        self.range = {k: [v[0], v[1]] for k, v in CAL_DEFAULT.items()}

    def to_position(self, name: str, angle: float) -> int:
        """각도 하나를 0~1000 정수 위치로 변환."""
        if angle is None or math.isnan(angle):
            return 0
        lo_open, hi_close = self.range[name]   # lo_open > hi_close 임에 주의
        if self.adaptive:
            if angle > lo_open:                # 폄 쪽으로 더 벌어졌다
                lo_open = self.range[name][0] = angle + self.margin
            if angle < hi_close:               # 쥠 쪽으로 더 굽었다
                hi_close = self.range[name][1] = angle - self.margin
        span = lo_open - hi_close
        if span < 1e-6:
            return 0
        ratio = (lo_open - angle) / span       # 0(폄) ~ 1(쥠)
        return int(max(POS_OPEN, min(POS_CLOSED, round(ratio * POS_CLOSED))))

    def axis_values(self, angles: dict) -> dict:
        """여섯 '계산 축'을 각각 0~1000 으로 정규화한다."""
        return {n: self.to_position(n, angles.get(n, float("nan")))
                for n in AXIS_NAMES}

    def compose(self, angles: dict, thumb_aux: str = "follow",
                aux_fixed: int = 0) -> list:
        """
        계산 축 → 로봇 배열 [엄지, 엄지보조, 검지, 중지, 약지, 소지].

        ■ 엄지보조(대립축)를 어떻게 정하는가 — 이 프로그램의 중요한 설계 판단

          기하 지표 5가지(중수골 각, 엄지방향 각, 손끝거리 2종, 투영거리)와
          'follow'(엄지와 동일)를, 정답을 아는 실사진 5장으로 실측 비교했다.
          각 후보에 최적 보정을 주고 저장소 프리셋과의 절대오차를 쟀다.
          측정 기록: 결과/엄지축_산출식_비교.txt

            후보              평균오차   최대오차
            C 엄지방향각          167      617
            D 소지MCP거리        177      393
            follow(엄지동일)      226      598
            E 검지MCP거리        232      582
            A 중수골각           342      873
            F 투영위치           828     1000   ← 부호가 반대라 값이 정반대

          핵심은 순위가 아니라 **어떤 후보도 OK 사인을 맞히지 못한다**는 점이다.
          최상위 C 도 133 을 내놓아 프리셋 750 과 617 만큼 어긋난다.
          사람 눈에는 OK 의 엄지가 '벌어져' 보이지만, 로봇은 엄지를 안으로 돌려야
          검지와 맞닿기 때문이다.
          즉 이 값은 사람 손 기하가 아니라 **로봇 기구학이 정하는 값**이며,
          2D 카메라 한 대로는 원리적으로 복원할 수 없다.

          C(167) 가 follow(226) 보다 근소하게 나으나, 표본 5장 안의 잡음과
          구분되지 않는다. 반면 follow 를 뒷받침하는 근거는 측정과 독립적이다.
            · hand_keyboard.py 제스처 9개 중 7개에서 엄지보조 == 엄지
              (나머지 2개도 OK +150, 하트 +100 차이뿐)
            · 제3자 독립 구현 szwedk/brainco-revo2-hand-control 의 POSES 도 같은 경향
            · 엄지와 엄지보조가 함께 움직여, 두 축이 따로 놀아 엄지가 어정쩡한
              자세로 걸리는 일이 구조적으로 생기지 않는다
          → 기본값 follow

        ■ 선택지
          follow : 엄지보조 = 엄지            (기본값, 권장)
          geom   : 엄지보조 = 엄지벌림 실측값  (후보 C 식. OK 사인은 어긋남)
          fixed  : 엄지보조 = 지정한 상수      (--aux-fixed)
        """
        av = self.axis_values(angles)
        thumb = int(round(THUMB_BLEND * av["엄지굽힘"]
                          + (1.0 - THUMB_BLEND) * av["엄지벌림"]))
        thumb = max(POS_OPEN, min(POS_CLOSED, thumb))
        if thumb_aux == "geom":
            aux = av["엄지벌림"]
        elif thumb_aux == "fixed":
            aux = max(POS_OPEN, min(POS_CLOSED, int(aux_fixed)))
        else:                                   # follow
            aux = thumb
        return [thumb, aux, av["검지"], av["중지"], av["약지"], av["소지"]]

    # 옛 이름 호환 (기존 시험 코드가 쓰던 이름)
    def positions_from_angles(self, angles: dict) -> list:
        return self.compose(angles)


class Smoother:
    """
    떨림 억제기.

    세 가지를 동시에 한다.
      1) 지수이동평균(EMA): 새 값 = a*측정 + (1-a)*직전     → 잔떨림 제거
      2) 최대 변화량 제한(slew): 한 번에 너무 크게 튀지 않게  → 급발진 방지
      3) 불감대(deadband): 변화가 미세하면 아예 안 보냄       → 모터 채터링 방지
    """

    def __init__(self, alpha: float = 0.35, max_step: int = 300, deadband: int = 12):
        self.alpha = alpha
        self.max_step = max_step
        self.deadband = deadband
        self.state = None      # 평활화된 실수 상태
        self.last_sent = None  # 마지막으로 실제 전송한 정수 배열

    def update(self, target: list) -> list:
        t = np.asarray(target, dtype=np.float64)
        if self.state is None:
            self.state = t.copy()
        else:
            nxt = self.alpha * t + (1.0 - self.alpha) * self.state
            delta = np.clip(nxt - self.state, -self.max_step, self.max_step)
            self.state = self.state + delta
        return [int(max(POS_OPEN, min(POS_CLOSED, round(v)))) for v in self.state]

    def should_send(self, positions: list) -> bool:
        """불감대보다 큰 변화가 있을 때만 True."""
        if self.last_sent is None:
            return True
        return max(abs(a - b) for a, b in zip(positions, self.last_sent)) >= self.deadband

    def mark_sent(self, positions: list):
        self.last_sent = list(positions)

    def reset(self):
        self.state = None
        self.last_sent = None


# ─────────────────────────────────────────────────────────────────────────────
# 출력 백엔드 — 로봇에 실제로 명령을 보내는 부분
#   세 종류가 같은 모양(connect / send / close)을 갖도록 만들어,
#   위쪽 추적 논리는 어떤 백엔드인지 몰라도 되게 했다.
# ─────────────────────────────────────────────────────────────────────────────

class BackendBase:
    name = "base"

    def connect(self):
        pass

    def send(self, positions, duration_ms=120):
        raise NotImplementedError

    def close(self):
        pass


class NoneBackend(BackendBase):
    """장비 없이 돌리는 모의 출력. 검증·연습용 기본값."""
    name = "none(모의)"

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.count = 0

    def send(self, positions, duration_ms=120):
        self.count += 1
        if self.verbose:
            print("  전송(모의) " + " ".join(f"{n}={v:4d}"
                  for n, v in zip(FINGER_NAMES, positions)))


class Ros2Backend(BackendBase):
    """
    경로 B. ROS 2 토픽 /set_motor_multi_127 로 SetMotorMulti 를 발행한다.
    저장소의 keyboard_control.py 와 완전히 같은 메시지 규격을 쓴다.
    ※ 별도 터미널에서 stark 컨트롤러 노드가 떠 있어야 한다.
    """
    name = "ros2"

    def __init__(self, slave_id=127, topic=None):
        self.slave_id = slave_id
        self.topic = topic or f"/set_motor_multi_{slave_id}"
        self.node = None
        self.pub = None
        self._rclpy = None
        self._msg_cls = None

    def connect(self):
        try:
            import rclpy
            from rclpy.node import Node
            from ros2_stark_msgs.msg import SetMotorMulti
        except ImportError as e:
            raise SystemExit(
                "[오류] ROS 2 환경을 불러오지 못했습니다: %s\n"
                "       먼저 다음을 실행한 뒤 다시 시도하십시오.\n"
                "         source /opt/ros/humble/setup.bash\n"
                "         source ~/ros2_ws/install/setup.bash   (stark 워크스페이스)\n"
                "       ROS 2 없이 시험만 하려면 --backend none 을 쓰십시오." % e)
        self._rclpy = rclpy
        self._msg_cls = SetMotorMulti
        rclpy.init()
        self.node = Node("hand_tracking_controller")
        self.pub = self.node.create_publisher(SetMotorMulti, self.topic, 10)
        time.sleep(0.5)     # 발행자 등록이 퍼질 시간
        self.node.get_logger().info(f"손추적 제어 시작 (토픽 {self.topic})")

    def send(self, positions, duration_ms=120):
        msg = self._msg_cls()
        msg.slave_id = self.slave_id
        msg.mode = 5                      # 5 = 위치 + 시간 모드
        msg.positions = list(positions)
        msg.speeds = [0] * N_FINGER
        msg.currents = [0] * N_FINGER
        msg.pwms = [0] * N_FINGER
        msg.durations = [int(duration_ms)] * N_FINGER
        self.pub.publish(msg)

    def close(self):
        try:
            if self.node is not None:
                self.node.destroy_node()
            if self._rclpy is not None:
                self._rclpy.shutdown()
        except Exception:
            pass


class SdkBackend(BackendBase):
    """
    경로 A. bc_stark_sdk 로 /dev/ttyUSB0 을 직접 잡아 제어한다. ROS 2 불필요.

    SDK 가 asyncio(비동기) 기반이라 별도 스레드에서 이벤트 루프를 돌리고,
    최신 목표값 하나만 큐에 담아 전달한다(밀린 명령이 쌓이지 않게).
    저장소 hand_keyboard.py 와 동일한 호출 규약을 따른다.
    """
    name = "sdk"

    def __init__(self, sdk_dir=None):
        self.sdk_dir = sdk_dir
        self.q = queue.Queue(maxsize=1)
        self.thread = None
        self.stop_evt = threading.Event()
        self.ready_evt = threading.Event()
        self.error = None
        self.slave_id = None
        self.client = None
        self.last_readback = None
        self.final_readback = None
        self.readback_every = 10      # 몇 번 보낼 때마다 실제 위치를 되읽을지

    # 제조사 SDK 예제를 찾아볼 위치들 (앞에서부터)
    #   2026년 기준 공식 저장소는 BrainCoTech/brainco-hand-sdk 이다.
    #   구 저장소 stark-serialport-example 도 아직 살아 있어 함께 찾는다.
    SDK_CANDIDATES = [
        "~/brainco-hand-sdk",
        "~/1/brainco/src/brainco-hand-sdk",
        "~/1/brainco/src/stark-serialport-example",
        "~/brainco-hand-sdk-main",
        "~/stark-serialport-example",
    ]

    def _resolve_sdk_dir(self):
        """SDK 예제 폴더 안의 python/revo2 경로를 찾는다."""
        cands = []
        if self.sdk_dir:
            cands.append(self.sdk_dir)
        if os.environ.get("STARK_SDK_DIR"):
            cands.append(os.environ["STARK_SDK_DIR"])
        cands += self.SDK_CANDIDATES
        tried = []
        for d in cands:
            revo2 = os.path.join(os.path.expanduser(d), "python", "revo2")
            tried.append(revo2)
            if os.path.isdir(revo2):
                return revo2
        raise SystemExit(
            "[오류] 제조사 SDK 예제 폴더를 찾지 못했습니다. 찾아본 곳:\n"
            + "".join(f"         {t}\n" for t in tried)
            + "       아래처럼 내려받은 뒤 다시 실행하십시오(MIT 라이선스).\n"
            "         git clone https://github.com/BrainCoTech/brainco-hand-sdk.git ~/brainco-hand-sdk\n"
            "         pip install bc-stark-sdk\n"
            "       설치 위치가 다르면:  export STARK_SDK_DIR=/내려받은/경로\n"
            "       로봇 없이 시험만 하려면 --backend none 을 쓰십시오.")

    def _worker(self):
        import asyncio
        # 폴더가 없으면 여기서 바로 알려야 한다.
        # (예전에는 이 예외가 작업 스레드 안에서 사라져, 본 스레드가 20초를
        #  헛되이 기다린 뒤 "시간 초과"라는 엉뚱한 진단을 냈다.)
        try:
            revo2 = self._resolve_sdk_dir()
        except SystemExit as e:
            self.error = str(e)
            self.ready_evt.set()
            return
        if revo2 not in sys.path:
            sys.path.insert(0, revo2)
        try:
            from bc_stark_sdk import main_mod as libstark
            from revo2_utils import open_modbus_revo2
        except ImportError as e:
            self.error = f"SDK import 실패: {e}"
            self.ready_evt.set()
            return

        async def run():
            client, slave_id = await open_modbus_revo2()
            self.slave_id = slave_id
            self.client = client
            # 위치를 0~1000 정규화 단위로 해석하도록 설정 (hand_keyboard.py 와 동일)
            await client.set_finger_unit_mode(slave_id, libstark.FingerUnitMode.Normalized)
            self.ready_evt.set()
            try:
                tick = 0
                while not self.stop_evt.is_set():
                    try:
                        positions, dur = self.q.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    await client.set_finger_positions_and_durations(
                        slave_id, list(positions), [int(dur)] * N_FINGER)
                    # 가끔 실제 위치를 되읽는다. 명령이 먹혔는지 확인하는 유일한 방법이다.
                    # 매번 읽으면 Modbus 왕복이 늘어 전송 주기가 무너지므로 10번에 1번만.
                    tick += 1
                    if self.readback_every > 0 and tick % self.readback_every == 0:
                        try:
                            self.last_readback = list(
                                await client.get_finger_positions(slave_id))
                        except Exception:
                            pass
            finally:
                # 끝내기 직전에 실제 위치를 한 번 읽어 둔다.
                # 명령이 정말 먹혔는지 확인할 수 있는 유일한 근거다.
                try:
                    self.last_readback = list(
                        await client.get_finger_positions(slave_id))
                except Exception:
                    pass
                # 안전: 반드시 손을 펴고 닫는다
                try:
                    await client.set_finger_positions_and_durations(
                        slave_id, [0] * N_FINGER, [500] * N_FINGER)
                    await asyncio.sleep(0.6)
                    self.final_readback = list(
                        await client.get_finger_positions(slave_id))
                except Exception:
                    pass
                libstark.modbus_close(client)

        # ★ asyncio.run() 을 쓰지 않는다.
        #   SDK 내부(Rust) 스레드가 파이썬 이벤트 루프로 콜백을 넣는데,
        #   asyncio.run() 이 루프를 즉시 닫아 버리면 그 콜백이
        #   "RuntimeError: Event loop is closed" 를 뱉는다.
        #   루프를 직접 만들고, 다 끝난 뒤 잠깐 더 돌려 콜백을 흘려보낸 다음 닫는다.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # 루프가 닫히는 순간에 들어오는 콜백의 예외는 무시한다(무해하다)
        loop.set_exception_handler(lambda l, ctx: None)
        try:
            loop.run_until_complete(run())
            loop.run_until_complete(asyncio.sleep(0.3))   # 잔여 콜백 배출
        except Exception as e:      # 연결 실패 등
            self.error = str(e)
            self.ready_evt.set()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass
            asyncio.set_event_loop(None)

    def connect(self):
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        if not self.ready_evt.wait(timeout=20):
            raise SystemExit("[오류] 로봇손 연결이 20초 안에 끝나지 않았습니다.\n"
                             "       24V DC 어댑터가 꽂혀 있는지 먼저 확인하십시오.\n"
                             "       (USB 는 통신 전용이라 전원 없이는 응답하지 않습니다)")
        if self.error:
            if self.error.lstrip().startswith("[오류]"):
                raise SystemExit(self.error)      # 이미 완성된 안내문이다
            raise SystemExit(f"[오류] 로봇손 연결 실패: {self.error}\n"
                             f"       ① 24V DC 어댑터 연결 확인 (가장 흔한 원인)\n"
                             f"          USB 는 통신 전용이라 전원 없이는 응답하지 않습니다\n"
                             f"       ② 포트 권한: id -nG | grep dialout 로 확인\n"
                             f"          없으면  sudo usermod -aG dialout $USER  후 재로그인\n"
                             f"          재로그인 없이 바로 쓰려면  sg dialout -c '<명령>'\n"
                             f"       ③ 다른 프로그램이 포트를 잡고 있는지: pkill -f stark_node")
        print(f"  로봇 연결됨 : slave_id {self.slave_id} (0x{self.slave_id:02X})")

    def send(self, positions, duration_ms=120):
        # 큐에는 항상 '가장 최신' 한 개만 둔다
        try:
            self.q.get_nowait()
        except queue.Empty:
            pass
        try:
            self.q.put_nowait((list(positions), duration_ms))
        except queue.Full:
            pass

    def close(self):
        self.stop_evt.set()
        if self.thread is not None:
            self.thread.join(timeout=5)


def make_backend(kind: str, slave_id: int, sdk_dir, verbose: bool) -> BackendBase:
    if kind == "ros2":
        return Ros2Backend(slave_id=slave_id)
    if kind == "sdk":
        return SdkBackend(sdk_dir=sdk_dir)
    return NoneBackend(verbose=verbose)


# ─────────────────────────────────────────────────────────────────────────────
# 화면 그리기 (한글 포함)
# ─────────────────────────────────────────────────────────────────────────────

class Overlay:
    """OpenCV 화면 위에 골격과 한글 글자를 그린다."""

    def __init__(self, font_size=22):
        from PIL import ImageFont
        self.font_path = None
        for path in FONT_CANDIDATES:
            if os.path.exists(path):
                self.font_path = path
                break
        self._ImageFont = ImageFont
        self._cache = {}
        self._scaled_for = None
        self.set_scale(font_size)

    def set_scale(self, font_size):
        """글자 크기를 바꾼다(해상도에 맞추기 위해 호출)."""
        F = self._ImageFont
        if self.font_path is None:
            self.font = self.font_small = F.load_default()
            self.font_path = "(기본 폰트 — 한글이 깨질 수 있음)"
            return
        key = int(font_size)
        if key not in self._cache:
            try:
                self._cache[key] = (F.truetype(self.font_path, key),
                                    F.truetype(self.font_path, max(11, int(key * 0.78))))
            except Exception:
                self._cache[key] = (F.load_default(), F.load_default())
        self.font, self.font_small = self._cache[key]

    def auto_scale(self, frame_h, frame_w):
        """
        영상 크기에 맞춰 글자·막대 치수를 정한다.

        왜 필요한가: 640x480 웹캠과 1080x1920 세로 영상은 픽셀 수가 8배 넘게
        차이 난다. 고정 22픽셀 글자를 쓰면 세로 영상에서는 글씨가 개미만 해진다.
        기준 높이 720 에 맞춘 배율을 써서 어느 해상도에서도 같은 비율로 보이게 한다.
        """
        if self._scaled_for == (frame_h, frame_w):
            return self.geom
        k = max(0.6, min(3.0, frame_h / 720.0))
        self.set_scale(int(22 * k))
        self.geom = {
            "pad":  int(14 * k),
            "bar_x": int(14 * k),
            "bar_y": int(56 * k),
            "bar_w": int(190 * k),
            "bar_h": int(20 * k),
            "gap":   int(32 * k),
            "label_x": int(214 * k),
            "line_w": max(2, int(2 * k)),
            "dot_r":  max(3, int(4 * k)),
            "tip_r":  max(4, int(6 * k)),
            "k": k,
        }
        self._scaled_for = (frame_h, frame_w)
        return self.geom

    def draw_skeleton(self, frame, pts_px):
        """21개 점과 연결선을 BGR 프레임에 직접 그린다."""
        import cv2
        g = getattr(self, "geom", None) or {"line_w": 2, "dot_r": 3, "tip_r": 5}
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, pts_px[a], pts_px[b], (0, 200, 255), g["line_w"], cv2.LINE_AA)
        for i, (x, y) in enumerate(pts_px):
            r = g["tip_r"] if i in (4, 8, 12, 16, 20) else g["dot_r"]   # 손끝은 크게
            cv2.circle(frame, (x, y), r, (0, 255, 0), -1, cv2.LINE_AA)

    def draw_texts(self, frame, items):
        """
        items = [(x, y, "문자열", (B,G,R), 크게?), ...]
        Pillow 로 그려야 한글이 나온다. cv2.putText 는 ASCII 전용이다.
        """
        import cv2
        from PIL import Image, ImageDraw
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(img)
        sw = max(2, int(3 * (getattr(self, "geom", {}) or {}).get("k", 1.0)))
        for x, y, text, bgr, big in items:
            rgb = (bgr[2], bgr[1], bgr[0])
            f = self.font if big else self.font_small
            # 어떤 배경에서도 읽히도록 검은 테두리를 두른다
            d.text((x, y), text, font=f, fill=(0, 0, 0),
                   stroke_width=sw, stroke_fill=(0, 0, 0))
            d.text((x, y), text, font=f, fill=rgb)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def draw_bars(self, frame, positions, x0=None, y0=None, w=None, h=None, gap=None):
        """손가락 6축의 0~1000 값을 막대 그래프로 그린다."""
        import cv2
        g = getattr(self, "geom", None) or {}
        x0 = g.get("bar_x", 14) if x0 is None else x0
        y0 = g.get("bar_y", 54) if y0 is None else y0
        w = g.get("bar_w", 190) if w is None else w
        h = g.get("bar_h", 18) if h is None else h
        gap = g.get("gap", 30) if gap is None else gap
        for i, v in enumerate(positions):
            y = y0 + i * gap
            cv2.rectangle(frame, (x0, y), (x0 + w, y + h), (60, 60, 60), -1)
            fill = int(w * v / POS_CLOSED)
            # 폄=초록 → 쥠=빨강 으로 색이 변한다
            color = (0, int(255 * (1 - v / POS_CLOSED)), int(255 * v / POS_CLOSED))
            if fill > 0:
                cv2.rectangle(frame, (x0, y), (x0 + fill, y + h), color, -1)
            cv2.rectangle(frame, (x0, y), (x0 + w, y + h), (220, 220, 220), 1)


# ─────────────────────────────────────────────────────────────────────────────
# 손 추적기 (MediaPipe Tasks API 감싸기)
# ─────────────────────────────────────────────────────────────────────────────

def find_model(explicit=None) -> str:
    """모델 파일(hand_landmarker.task) 경로를 찾는다. 없으면 안내 후 종료."""
    # 사용자가 --model 로 경로를 콕 집어 줬는데 그 파일이 없으면,
    # 조용히 다른 모델로 넘어가면 안 된다. 지정한 것이 없다고 알려야 한다.
    if explicit:
        ep = os.path.abspath(os.path.expanduser(explicit))
        if not os.path.isfile(ep):
            raise SystemExit(f"[오류] --model 로 지정한 파일이 없습니다: {ep}")
        return ep
    cands = list(MODEL_CANDIDATES)
    for c in cands:
        if c and os.path.isfile(os.path.abspath(os.path.expanduser(c))):
            return os.path.abspath(os.path.expanduser(c))
    raise SystemExit(
        "[오류] 손 랜드마크 모델 파일을 찾지 못했습니다.\n"
        "       아래 명령으로 내려받으십시오(약 7.8MB).\n"
        f"         mkdir -p models && curl -L -o models/hand_landmarker.task \\\n"
        f"           {MODEL_URL}\n"
        "       또는 --model 로 경로를 직접 지정하십시오.")


class HandTracker:
    """MediaPipe HandLandmarker 를 영상/이미지 모드로 감싼 것."""

    def __init__(self, model_path, num_hands=1, det_conf=0.5, pres_conf=0.5,
                 track_conf=0.5, video_mode=True):
        import mediapipe as mp
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision
        self.mp = mp
        self.vision = vision
        mode = vision.RunningMode.VIDEO if video_mode else vision.RunningMode.IMAGE
        self.video_mode = video_mode
        opts = vision.HandLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=model_path),
            running_mode=mode,
            num_hands=num_hands,
            min_hand_detection_confidence=det_conf,
            min_hand_presence_confidence=pres_conf,
            min_tracking_confidence=track_conf,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(opts)
        self._closed = False

    def detect(self, bgr_frame, timestamp_ms):
        import cv2
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        mp_img = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        if self.video_mode:
            return self.landmarker.detect_for_video(mp_img, int(timestamp_ms))
        return self.landmarker.detect(mp_img)

    def close(self):
        # mediapipe 1.0.1 은 인터프리터 종료 중에 __del__ 이 돌면
        # TypeError: 'NoneType' object is not callable 을 뱉는다.
        # 그래서 반드시 우리가 먼저 명시적으로 닫아준다.
        if not self._closed:
            try:
                self.landmarker.close()
            except Exception:
                pass
            self._closed = True


# ─────────────────────────────────────────────────────────────────────────────
# 영상 입력
# ─────────────────────────────────────────────────────────────────────────────

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

# 입력이 이보다 작으면 확대한다 (짧은 변 기준, 픽셀)
DEFAULT_MIN_SIZE = 320


def ensure_min_size(frame, min_size=DEFAULT_MIN_SIZE):
    """
    너무 작은 그림은 확대해서 돌려준다. (작으면 원본 그대로)

    ★ 왜 필요한가 — 실측으로 확인한 함정
      MediaPipe 는 입력 화소가 부족하면 '검출은 되지만 관절 위치가 틀린' 상태가 된다.
      25x75 픽셀짜리 손동작 아이콘으로 시험했더니,
        원본(25x75) → 검지=947(굽힘) 소지= 99(폄)   ← 완전히 반대
        4배 확대     → 검지=101(폄)  소지=934(굽힘)  ← 정답
      이었다. 오류로 멈추지 않고 조용히 틀린 값을 내므로 특히 위험하다.

      웹캠(보통 640x480 이상)에서는 발동하지 않는다. 작은 사진·썸네일·
      저해상도 스트림을 넣었을 때만 동작하는 안전장치다.
    """
    import cv2
    h, w = frame.shape[:2]
    short = min(h, w)
    if short >= min_size or short <= 0:
        return frame, 1.0
    k = float(min_size) / short
    return cv2.resize(frame, (int(round(w * k)), int(round(h * k))),
                      interpolation=cv2.INTER_CUBIC), k


def open_source(source: str):
    """
    --source 문자열을 해석해 (VideoCapture, 종류, 총프레임수, fps) 를 돌려준다.
    종류: "camera" | "video" | "image"
    """
    import cv2
    if source.isdigit():
        idx = int(source)
        dev = f"/dev/video{idx}"
        if os.name == "posix" and not os.path.exists(dev):
            raise SystemExit(
                f"[오류] 카메라 장치 {dev} 가 없습니다.\n"
                f"       이 컴퓨터에 웹캠이 연결되어 있는지 확인하십시오.\n"
                f"         ls /dev/video*        ← 아무것도 안 나오면 카메라 없음\n"
                f"       카메라 없이 시험하려면 영상 파일을 넣으십시오.\n"
                f"         --source 어떤영상.mp4")
        # V4L2 를 명시한다. 생략하면 실패 시 FFMPEG 로 되돌아가 엉뚱한 장치가 열린다.
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise SystemExit(
                f"[오류] 카메라 {idx} 번을 열 수 없습니다.\n"
                f"       ① 다른 프로그램이 쓰고 있는지 확인: fuser -v {dev}\n"
                f"       ② 쓸 수 있는 장치 목록 확인: --list-cameras")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        ok, _probe = cap.read()
        if not ok:
            cap.release()
            raise SystemExit(
                f"[오류] 카메라 {idx} 번은 열렸지만 영상이 나오지 않습니다.\n"
                f"       메타데이터 전용 장치일 수 있습니다. --list-cameras 로 확인하십시오.")
        return cap, "camera", 0, 30.0

    path = os.path.expanduser(source)
    if not os.path.exists(path):
        raise SystemExit(f"[오류] 입력 파일이 없습니다: {path}")
    if path.lower().endswith(IMAGE_EXT):
        return None, "image", 1, 0.0

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"[오류] 영상 파일을 열 수 없습니다: {path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    return cap, "video", total, fps


# ─────────────────────────────────────────────────────────────────────────────
# 자체 시험 — 카메라도 로봇도 없이 계산 논리를 검증한다
# ─────────────────────────────────────────────────────────────────────────────

def synth_hand(curl: float) -> np.ndarray:
    """
    시험용 가짜 손 좌표 21점을 만든다.
    curl=0 이면 손가락이 곧게 펴진 손, curl=1 이면 굽은 손을 만든다.
    (실제 사람 손이 아니라, 각도 계산식이 옳게 반응하는지만 확인하는 용도)
    """
    pts = np.zeros((21, 3))
    pts[WRIST] = [0.0, 0.0, 0.0]
    # 엄지: 옆으로 벌어졌다가 curl 이 커지면 손바닥 쪽으로 붙는다
    spread = math.radians(50 - 35 * curl)
    pts[THUMB_CMC] = [-0.20 * math.sin(spread), 0.20 * math.cos(spread), 0]
    pts[THUMB_MCP] = [-0.36 * math.sin(spread), 0.36 * math.cos(spread), 0]
    bend_t = math.radians(10 + 50 * curl)
    d = np.array([-math.sin(spread + bend_t), math.cos(spread + bend_t), 0.0])
    pts[THUMB_IP] = pts[THUMB_MCP] + 0.16 * d
    d2 = np.array([-math.sin(spread + 2 * bend_t), math.cos(spread + 2 * bend_t), 0.0])
    pts[THUMB_TIP] = pts[THUMB_IP] + 0.13 * d2
    # 네 손가락: 손목에서 위로 뻗은 뒤 각 관절이 curl 만큼 굽는다
    for k, (mcp, pip, dip, tip) in enumerate(FOUR_FINGER_JOINTS.values()):
        x = 0.10 + 0.09 * k
        pts[mcp] = [x, 0.42, 0.0]
        theta = math.radians(90.0)                    # 위쪽 방향
        seg = [0.20, 0.13, 0.10]
        joint_bend = math.radians(80.0 * curl)
        prev = pts[mcp].copy()
        cur_theta = theta
        for j, (idx, L) in enumerate(zip((pip, dip, tip), seg)):
            cur_theta -= joint_bend if j > 0 else joint_bend * 0.6
            prev = prev + L * np.array([math.cos(cur_theta), math.sin(cur_theta), 0.0])
            pts[idx] = prev
    pts[INDEX_MCP] = pts[5]
    return pts


def run_self_test() -> int:
    """장비 없이 계산 논리를 점검한다. 모두 통과하면 0 을 돌려준다."""
    print("=" * 74)
    print(" 자체 시험 — 카메라·로봇 없이 계산 논리만 검증합니다")
    print("=" * 74)
    fails = []

    # 1. 각도 계산이 기본 도형에서 맞는가
    print("\n[1] 각도 계산 기본 검증")
    cases = [
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), 90.0, "직각"),
        ((0, 0, 0), (1, 0, 0), (-1, 0, 0), 180.0, "일직선"),
        ((0, 0, 0), (1, 0, 0), (1, 0, 0), 0.0, "같은 방향"),
    ]
    for b, a, c, want, label in cases:
        got = angle_at(b, a, c)
        ok = abs(got - want) < 1e-6
        print(f"    {'통과' if ok else '실패'}  {label}: 기대 {want}도, 실제 {got:.4f}도")
        if not ok:
            fails.append(f"각도 {label}")

    # 2. 배열 순서와 이름이 규약과 맞는가
    print("\n[2] 손가락 배열 순서 검증")
    want_order = ["엄지", "엄지보조", "검지", "중지", "약지", "소지"]
    ok = FINGER_NAMES == want_order
    print(f"    {'통과' if ok else '실패'}  {FINGER_NAMES}")
    if not ok:
        fails.append("배열 순서")

    # 3. 폄→쥠 으로 갈수록 위치값이 커지는가 (단조 증가)
    print("\n[3] 굽힘 정도에 따른 위치값 단조성 검증")
    cal = Calibrator(adaptive=False)
    rows = []
    for curl in (0.0, 0.25, 0.5, 0.75, 1.0):
        ang = compute_raw_angles(synth_hand(curl))
        pos = cal.compose(ang)
        rows.append((curl, pos))
        print(f"    curl={curl:.2f} → " + " ".join(f"{n}={v:4d}" for n, v in zip(FINGER_NAMES, pos)))
    for i in range(N_FINGER):
        seq = [r[1][i] for r in rows]
        if not all(seq[j] <= seq[j + 1] for j in range(len(seq) - 1)):
            print(f"    실패  {FINGER_NAMES[i]} 가 단조 증가하지 않음: {seq}")
            fails.append(f"단조성 {FINGER_NAMES[i]}")
    if not any(f.startswith("단조성") for f in fails):
        print("    통과  여섯 축 모두 폄→쥠 방향으로 단조 증가")

    # 4. 크기 불변성: 손을 2배로 키워도 같은 값이 나오는가
    print("\n[4] 손 크기 불변성 검증 (구판 거리비 방식의 결함 확인)")
    base = synth_hand(0.5)
    big = base * 3.0
    p1 = Calibrator(adaptive=False).compose(compute_raw_angles(base))
    p2 = Calibrator(adaptive=False).compose(compute_raw_angles(big))
    ok = p1 == p2
    print(f"    {'통과' if ok else '실패'}  원본 {p1}")
    print(f"           3배   {p2}")
    if not ok:
        fails.append("크기 불변성")

    # 5. 평활기 동작
    print("\n[5] 떨림 억제기 검증")
    sm = Smoother(alpha=0.5, max_step=100, deadband=10)
    a = sm.update([1000] * 6)
    ok = all(v <= 1000 for v in a)
    print(f"    {'통과' if ok else '실패'}  첫 갱신 결과 {a} (초기값이므로 목표와 같아야 함)")
    sm2 = Smoother(alpha=1.0, max_step=100, deadband=10)
    sm2.update([0] * 6)
    b = sm2.update([1000] * 6)
    ok2 = b == [100] * 6
    print(f"    {'통과' if ok2 else '실패'}  최대 변화량 제한 100 적용 결과 {b} (기대 [100]*6)")
    if not ok2:
        fails.append("slew 제한")
    sm2.mark_sent(b)
    ok3 = (sm2.should_send([v + 3 for v in b]) is False)
    print(f"    {'통과' if ok3 else '실패'}  불감대: 3 만큼 변화는 전송하지 않음")
    if not ok3:
        fails.append("불감대")

    # 6. 백엔드 인터페이스
    print("\n[6] 엄지보조(대립축) 결정법 검증")
    ang = compute_raw_angles(synth_hand(0.8))
    c2 = Calibrator(adaptive=False)
    pf = c2.compose(ang, "follow")
    pg = c2.compose(ang, "geom")
    px = c2.compose(ang, "fixed", 777)
    ok = (pf[1] == pf[0])
    print(f"    {'통과' if ok else '실패'}  follow: 엄지보조({pf[1]}) == 엄지({pf[0]})")
    if not ok:
        fails.append("thumb-aux follow")
    ok = (pg[1] == c2.axis_values(ang)["엄지벌림"])
    print(f"    {'통과' if ok else '실패'}  geom  : 엄지보조({pg[1]}) == 엄지벌림 실측값")
    if not ok:
        fails.append("thumb-aux geom")
    ok = (px[1] == 777)
    print(f"    {'통과' if ok else '실패'}  fixed : 엄지보조({px[1]}) == 지정값 777")
    if not ok:
        fails.append("thumb-aux fixed")
    # 나머지 5칸은 방식과 무관하게 같아야 한다
    ok = (pf[0::2][1:] == pg[0::2][1:]) and (pf[2:] == pg[2:] == px[2:])
    print(f"    {'통과' if ok else '실패'}  네 손가락 값은 방식과 무관하게 동일")
    if not ok:
        fails.append("thumb-aux 부작용")

    print("\n[7] 최소 해상도 보장 검증")
    try:
        import cv2 as _cv2
        small = np.zeros((75, 25, 3), dtype=np.uint8)
        big, k = ensure_min_size(small, 320)
        ok = (min(big.shape[:2]) >= 320) and k > 1.0
        print(f"    {'통과' if ok else '실패'}  25x75 → {big.shape[1]}x{big.shape[0]} (배율 {k:.1f})")
        if not ok:
            fails.append("최소 해상도 확대")
        keep, k2 = ensure_min_size(np.zeros((480, 640, 3), dtype=np.uint8), 320)
        ok2 = (keep.shape[:2] == (480, 640)) and k2 == 1.0
        print(f"    {'통과' if ok2 else '실패'}  640x480 은 그대로 둠 (배율 {k2:.1f})")
        if not ok2:
            fails.append("최소 해상도 무변경")
    except Exception as e:
        print(f"    실패  {type(e).__name__}: {e}")
        fails.append("최소 해상도")

    print("\n[8] 모의 백엔드 검증")
    be = NoneBackend()
    be.connect(); be.send([0] * 6); be.send([500] * 6); be.close()
    ok = be.count == 2
    print(f"    {'통과' if ok else '실패'}  전송 횟수 {be.count} (기대 2)")
    if not ok:
        fails.append("모의 백엔드")

    print("\n" + "=" * 74)
    if fails:
        print(f" 결과: 실패 {len(fails)}건 — {', '.join(fails)}")
        return 1
    print(" 결과: 전 항목 통과")
    print("=" * 74)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# 본체
# ─────────────────────────────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        prog="hand_tracking_control.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="카메라로 사람 손을 추적해 BrainCo Revo2 로봇손이 따라 하게 합니다.",
        epilog=(
            "예시\n"
            "  python3 hand_tracking_control.py                       웹캠, 모의출력\n"
            "  python3 hand_tracking_control.py --backend sdk         로봇 직접 제어\n"
            "  python3 hand_tracking_control.py --backend ros2        ROS 2 경유\n"
            "  python3 hand_tracking_control.py --source 손.mp4 --headless \\\n"
            "        --record 결과/주석영상.mp4 --csv 결과/기록.csv\n"
            "  python3 hand_tracking_control.py --self-test           장비 없이 논리 검증\n"))
    p.add_argument("--source", default="0",
                   help="입력. 웹캠 번호(0,1,…) 또는 영상/이미지 파일 경로. 기본 0")
    p.add_argument("--backend", choices=["none", "ros2", "sdk"], default="none",
                   help="출력. none=모의(기본), ros2=토픽 발행, sdk=시리얼 직접")
    p.add_argument("--model", default=None, help="hand_landmarker.task 경로")
    p.add_argument("--slave-id", type=int, default=127, help="Modbus slave id. 오른손 127")
    p.add_argument("--sdk-dir", default=None, help="공식 SDK 예제 폴더(=STARK_SDK_DIR)")
    p.add_argument("--geom", choices=["world", "screen2d", "screen3d"], default="screen2d",
                   help="각도 계산에 쓸 좌표. screen2d=화면 x,y (기본, 가장 안정적) / "
                        "world=미터 단위 3D / screen3d=화면 x,y,z")
    p.add_argument("--alpha", type=float, default=0.35, help="평활 계수 0~1. 작을수록 부드럽고 느림")
    p.add_argument("--max-step", type=int, default=300, help="1회 최대 변화량(0~1000 단위)")
    p.add_argument("--deadband", type=int, default=12, help="이 값보다 작은 변화는 전송 생략")
    p.add_argument("--rate", type=float, default=20.0, help="초당 최대 전송 횟수")
    p.add_argument("--duration", type=int, default=120, help="로봇 동작 시간(ms)")
    p.add_argument("--thumb-aux", choices=["follow", "geom", "fixed"], default="follow",
                   help="엄지보조(대립축) 결정법. follow=엄지와 동일(기본, 저장소 관례) / "
                        "geom=기하 실측 / fixed=고정값")
    p.add_argument("--aux-fixed", type=int, default=0,
                   help="--thumb-aux fixed 일 때 쓸 값 0~1000")
    p.add_argument("--no-adaptive", action="store_true", help="가동범위 자동 확장 끄기")
    p.add_argument("--no-mirror", action="store_true", help="좌우 반전(거울) 끄기")
    p.add_argument("--relax-timeout", type=float, default=3.0,
                   help="손을 이만큼(초) 못 찾으면 스스로 손을 편다. 0=사용 안 함")
    p.add_argument("--headless", action="store_true", help="창을 띄우지 않음(서버·원격용)")
    p.add_argument("--record", default=None, help="주석 입힌 영상을 이 경로에 저장")
    p.add_argument("--csv", default=None, help="프레임별 위치값을 이 CSV 에 기록")
    p.add_argument("--readback", action="store_true",
                   help="로봇에서 실제 손가락 위치를 되읽어 CSV 에 함께 기록한다. "
                        "명령이 정말 먹혔는지 대조할 수 있다(--backend sdk 전용, 전송 주기가 조금 느려짐)")
    p.add_argument("--pace", choices=["auto", "on", "off"], default="auto",
                   help="영상 파일을 원래 속도로 재생한다. auto=로봇에 연결됐을 때만 켬(기본). "
                        "끄면 최대 속도로 처리해 로봇이 따라오지 못한다")
    p.add_argument("--min-size", type=int, default=DEFAULT_MIN_SIZE,
                   help="입력의 짧은 변이 이보다 작으면 확대한다(픽셀). 0=사용 안 함. "
                        "해상도가 낮으면 MediaPipe 가 조용히 틀린 값을 낸다")
    p.add_argument("--max-frames", type=int, default=0, help="이만큼 처리하고 종료. 0=제한없음")
    p.add_argument("--verbose", action="store_true", help="전송값을 터미널에 계속 출력")
    p.add_argument("--self-test", action="store_true", help="장비 없이 계산 논리만 검증")
    p.add_argument("--list-cameras", action="store_true", help="연결된 카메라 목록 확인")
    return p


def list_cameras():
    print("연결된 카메라 장치를 확인합니다.")
    import glob
    devs = sorted(glob.glob("/dev/video*"))
    if not devs:
        print("  없음. 이 컴퓨터에는 웹캠이 연결되어 있지 않습니다.")
        print("  → USB 웹캠을 꽂거나, --source 영상파일.mp4 로 시험하십시오.")
        return 1
    import cv2
    usable = 0
    for d in sorted(devs, key=lambda x: int(x.replace("/dev/video", ""))):
        idx = int(d.replace("/dev/video", ""))
        # ★ 반드시 V4L2 백엔드를 지정해야 한다.
        #   지정하지 않으면 OpenCV 가 실패한 뒤 FFMPEG 로 되돌아가서,
        #   메타데이터 전용 장치(/dev/video1 등)까지 '사용 가능'으로 잘못 보고한다.
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if cap.isOpened():
            ok, fr = cap.read()
            if ok and fr is not None:
                print(f"  {d}  사용 가능  해상도 {fr.shape[1]}x{fr.shape[0]}  → --source {idx}")
                usable += 1
            else:
                print(f"  {d}  영상이 나오지 않음 (메타데이터 전용 장치)")
            cap.release()
        else:
            print(f"  {d}  V4L2 로 열 수 없음 (메타데이터 전용 장치이거나 사용 중)")
    if usable == 0:
        print("  → 쓸 수 있는 카메라가 없습니다. 영상 파일로 시험하십시오: --source 영상.mp4")
        return 1
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return run_self_test()
    if args.list_cameras:
        return list_cameras()

    import cv2

    model_path = find_model(args.model)
    cap, kind, total, src_fps = open_source(args.source)
    is_image = (kind == "image")

    tracker = HandTracker(model_path, num_hands=1, video_mode=not is_image)
    cal = Calibrator(adaptive=not args.no_adaptive)
    sm = Smoother(alpha=args.alpha, max_step=args.max_step, deadband=args.deadband)
    overlay = Overlay()          # 화면 표시에도, 영상 기록에도 필요하다

    backend = make_backend(args.backend, args.slave_id, args.sdk_dir, args.verbose)
    if args.readback and isinstance(backend, SdkBackend):
        backend.readback_every = 1      # 보낼 때마다 실제 위치를 읽는다

    print("=" * 74)
    print(" BrainCo Revo2 — 카메라 손추적 추종 제어")
    print("=" * 74)
    print(f"  입력      : {args.source}  ({ {'camera':'웹캠','video':'영상파일','image':'이미지'}[kind] })")
    print(f"  출력      : {backend.name}")
    print(f"  모델      : {model_path}")
    print(f"  좌표방식  : {args.geom}")
    if kind == "video":
        _p = (args.pace == "on" or (args.pace == "auto" and args.backend != "none"))
        print(f"  재생속도  : {'원래 속도로 맞춤' if _p else '최대 속도'}")
    print(f"  최소해상도: {args.min_size}픽셀" + (" (사용 안 함)" if args.min_size <= 0 else ""))
    print(f"  글꼴      : {overlay.font_path}")
    print(f"  배열순서  : {FINGER_NAMES}  (0=폄, 1000=쥠)")
    print(f"  엄지보조  : {args.thumb_aux}"
          + (f" ({args.aux_fixed})" if args.thumb_aux == 'fixed' else ""))
    if not args.headless and kind != "image":
        print("\n  조작 : q 종료 | c 가동범위 초기화 | space 일시정지 | o 손 펴기")
    print("=" * 74 + "\n")

    # 연결에 실패해 여기서 중단되더라도 MediaPipe 를 반드시 먼저 닫아야 한다.
    # 닫지 않고 인터프리터가 내려가면 mediapipe 1.0.1 의 __del__ 이
    # "TypeError: 'NoneType' object is not callable" 역추적을 뱉는다.
    try:
        backend.connect()
    except BaseException:
        tracker.close()
        raise

    writer = None
    csv_f = csv_w = None
    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)) or ".", exist_ok=True)
        csv_f = open(args.csv, "w", newline="", encoding="utf-8-sig")
        csv_w = csv.writer(csv_f)
        header = (["frame", "time_s", "detected", "handedness", "score"]
                  + [f"pos_{n}" for n in FINGER_NAMES_EN]
                  + [f"angle_{n}" for n in AXIS_NAMES_EN])
        if args.readback:
            header += [f"actual_{n}" for n in FINGER_NAMES_EN]
        csv_w.writerow(header)

    # ── 영상 파일 재생 속도 맞춤 ────────────────────────────────────────────
    #   영상은 파일에서 읽는 만큼 빠르게 처리된다. 이 PC 에서는 40초짜리 영상이
    #   16초 만에 끝났다. 화면만 볼 때는 상관없지만, 로봇을 붙이면
    #   손가락이 물리적으로 움직일 시간보다 명령이 빨리 도착해 동작이 뭉개진다.
    #   그래서 로봇에 연결됐을 때는 원래 속도(초당 프레임 수)로 늦춘다.
    pacing = (kind == "video") and (
        args.pace == "on" or (args.pace == "auto" and args.backend != "none"))
    frame_interval = (1.0 / src_fps) if (src_fps and src_fps > 0) else 0.0

    sent_count = 0
    frame_idx = 0
    detected_count = 0
    last_send = 0.0
    last_seen = time.time()
    paused = False
    t_start = time.time()
    min_send_gap = 1.0 / max(1e-6, args.rate)

    # 안전: 시작할 때 손을 편다
    backend.send([0] * N_FINGER, 500)
    sm.mark_sent([0] * N_FINGER)

    try:
        while True:
            if is_image:
                frame = cv2.imread(os.path.expanduser(args.source))
                if frame is None:
                    raise SystemExit(f"[오류] 이미지를 읽을 수 없습니다: {args.source}")
            else:
                if paused:
                    key = cv2.waitKey(30) & 0xFF
                    if key == ord(" "):
                        paused = False
                    elif key == ord("q"):
                        break
                    continue
                ok, frame = cap.read()
                if not ok:
                    print("\n[알림] 입력이 끝났습니다.")
                    break

            if kind == "camera" and not args.no_mirror:
                frame = cv2.flip(frame, 1)      # 거울 모드: 내 손과 화면이 같은 쪽

            # 해상도가 부족하면 확대한다(위 ensure_min_size 주석 참조)
            if args.min_size > 0:
                frame, _upscale = ensure_min_size(frame, args.min_size)
                if frame_idx == 0 and _upscale > 1.0:
                    print(f"[알림] 입력이 작아 {_upscale:.1f}배로 확대합니다"
                          f" (짧은 변 {args.min_size}픽셀 기준). MediaPipe 오검출 방지.")

            h, w = frame.shape[:2]
            ts_ms = int((frame_idx / (src_fps if src_fps > 0 else 30.0)) * 1000) \
                if kind == "video" else int(time.time() * 1000)

            result = tracker.detect(frame, ts_ms)

            positions = None
            angles = {}
            handed, score = "", 0.0

            if result.hand_landmarks:
                detected_count += 1
                last_seen = time.time()
                lms = result.hand_landmarks[0]
                if result.handedness:
                    handed = result.handedness[0][0].category_name
                    score = float(result.handedness[0][0].score)

                # 각도 계산에 쓸 좌표를 고른다
                if args.geom == "world" and getattr(result, "hand_world_landmarks", None):
                    pts = landmarks_to_array(result.hand_world_landmarks[0], use_z=True)
                else:
                    pts = landmarks_to_array(lms, use_z=(args.geom == "screen3d"))
                    # 화면 좌표는 x 가 0~1, y 도 0~1 이라 가로세로 비가 왜곡돼 있다.
                    # 각도를 재려면 실제 화면 비율로 되돌려야 한다.
                    pts[:, 0] *= w
                    pts[:, 1] *= h
                    if args.geom == "screen3d":
                        pts[:, 2] *= w

                angles = compute_raw_angles(pts)
                raw_pos = cal.compose(angles, args.thumb_aux, args.aux_fixed)
                positions = sm.update(raw_pos)

                if not args.headless or args.record:
                    px = [(int(p.x * w), int(p.y * h)) for p in lms]
                    overlay.draw_skeleton(frame, px)

            else:
                # 손을 놓쳤다 — 일정 시간이 지나면 안전하게 편다
                if args.relax_timeout > 0 and (time.time() - last_seen) > args.relax_timeout:
                    positions = sm.update([0] * N_FINGER)

            # ── 로봇으로 전송 (전송률 제한 + 불감대) ──────────────────────
            now = time.time()
            if positions is not None and (now - last_send) >= min_send_gap:
                if sm.should_send(positions):
                    backend.send(positions, args.duration)
                    sm.mark_sent(positions)
                    sent_count += 1
                    if args.verbose:
                        print(f"  #{frame_idx:5d} " +
                              " ".join(f"{n}={v:4d}" for n, v in zip(FINGER_NAMES, positions)))
                last_send = now

            if csv_w is not None:
                pv = positions if positions is not None else [""] * N_FINGER
                av = [round(angles[n], 2) if n in angles and not math.isnan(angles[n]) else ""
                      for n in AXIS_NAMES]
                row = ([frame_idx, round(now - t_start, 3),
                        int(bool(result.hand_landmarks)), handed, round(score, 3)]
                       + list(pv) + av)
                if args.readback:
                    ab = getattr(backend, "last_readback", None)
                    row += (list(ab) if ab else [""] * N_FINGER)
                csv_w.writerow(row)

            # ── 화면 구성 ────────────────────────────────────────────────
            if not args.headless or args.record:
                g = overlay.auto_scale(h, w)
                shown = positions if positions is not None else [0] * N_FINGER
                overlay.draw_bars(frame, shown)
                items = []
                if result.hand_landmarks:
                    items.append((g["pad"], g["pad"], f"손 검출  {handed} {score:.2f}",
                                  (0, 255, 120), True))
                else:
                    items.append((g["pad"], g["pad"], "손을 카메라에 보여주세요",
                                  (60, 60, 255), True))
                for i, (n, v) in enumerate(zip(FINGER_NAMES, shown)):
                    items.append((g["label_x"], g["bar_y"] + i * g["gap"] - int(2 * g["k"]),
                                  f"{n} {v:4d}", (255, 255, 255), False))
                fps_now = frame_idx / max(1e-6, now - t_start)
                items.append((g["pad"], h - int(34 * g["k"]),
                              f"{frame_idx}프레임  {fps_now:4.1f}fps  전송 {sent_count}회  출력={backend.name}",
                              (200, 200, 200), False))
                frame = overlay.draw_texts(frame, items)

                if args.record and writer is None:
                    os.makedirs(os.path.dirname(os.path.abspath(args.record)) or ".", exist_ok=True)
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    out_fps = src_fps if src_fps and src_fps > 1 else 20.0
                    writer = cv2.VideoWriter(args.record, fourcc, out_fps, (w, h))
                    if not writer.isOpened():
                        print(f"[경고] 녹화 파일을 열 수 없습니다: {args.record}")
                        writer = None
                if writer is not None:
                    writer.write(frame)

            if not args.headless:
                cv2.imshow("BrainCo Revo2 - 손추적 제어 (q=종료)", frame)
                key = cv2.waitKey(1 if not is_image else 0) & 0xFF
                if key == ord("q") or key == 27:
                    break
                elif key == ord("c"):
                    cal.reset(); sm.reset()
                    print("[알림] 가동범위를 표준값으로 초기화했습니다.")
                elif key == ord(" "):
                    paused = True
                elif key == ord("o"):
                    backend.send([0] * N_FINGER, 500); sm.reset()
                    print("[알림] 손을 폈습니다.")

            # 영상을 원래 속도로 재생해야 한다면 남는 시간만큼 쉰다
            if pacing and frame_interval > 0:
                due = t_start + (frame_idx + 1) * frame_interval
                lag = due - time.time()
                if lag > 0:
                    time.sleep(lag)

            frame_idx += 1
            if is_image:
                break
            if args.max_frames and frame_idx >= args.max_frames:
                print(f"\n[알림] 지정한 {args.max_frames} 프레임을 처리했습니다.")
                break

    except KeyboardInterrupt:
        print("\n[알림] 사용자가 중단했습니다(Ctrl+C).")
    finally:
        # ── 안전 종료: 반드시 손을 펴고 끝낸다 ───────────────────────────
        try:
            backend.send([0] * N_FINGER, 500)
            time.sleep(0.4)
        except Exception:
            pass
        backend.close()
        tracker.close()
        if writer is not None:
            writer.release()
        if csv_f is not None:
            csv_f.close()
        if cap is not None:
            cap.release()
        if not args.headless:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass

    dur = time.time() - t_start
    print("\n" + "=" * 74)
    print(" 요약")
    print("=" * 74)
    print(f"  처리 프레임 : {frame_idx}")
    print(f"  손 검출     : {detected_count} 프레임"
          f"  ({100.0*detected_count/max(1,frame_idx):.1f}%)")
    print(f"  로봇 전송   : {sent_count} 회")
    print(f"  소요 시간   : {dur:.1f} 초  (평균 {frame_idx/max(1e-6,dur):.1f} fps)")
    rb = getattr(backend, "last_readback", None)
    if rb is not None:
        print(f"  로봇 실측값 : {rb}   ← 종료 직전 로봇에서 되읽은 실제 위치")
    fb = getattr(backend, "final_readback", None)
    if fb is not None:
        print(f"  안전 종료   : {fb}   ← 손을 편 뒤 되읽은 값(전부 0 이어야 정상)")
    if args.record:
        print(f"  주석 영상   : {args.record}")
    if args.csv:
        print(f"  기록 CSV    : {args.csv}")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
