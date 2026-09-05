#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 pi2jw
# Licensed under the Apache License, Version 2.0. See ../LICENSE
#
"""
================================================================================
 제스처 의미 검증 — "펴야 할 손가락이 정말 낮게 나오는가"
================================================================================

■ 무엇을 확인하는가
   프로그램이 죽지 않는다는 것만으로는 "맞게 동작한다"고 말할 수 없다.
   여기서는 정답을 아는 손동작 사진을 넣고,
       펴야 하는 손가락의 위치값 평균  <  굽혀야 하는 손가락의 위치값 평균
   이 성립하는지 검사한다. 이 기준은 사람마다 다른 절대 가동범위와 무관하므로
   보정 상태에 흔들리지 않는다.

■ 왜 이 검사가 구판의 결함을 잡아내는가
   구판은 배열이 [엄지, 검지, 중지, 약지, 소지, 손목] 이라
   '엄지보조' 자리에 검지 값이 들어간다. 그 상태로 이 검사를 돌리면
   브이·엄지척 같은 제스처에서 굽힘/폄이 뒤바뀌어 반드시 실패한다.

■ ★ 시험 자료를 고를 때의 함정 (실측으로 확인함)
   1) 해상도가 낮으면 안 된다.
      위키미디어의 손동작 아이콘 원본은 25x75 픽셀이다. 그대로 넣으면
      MediaPipe 가 '검출은 되지만 손가락이 뒤바뀐' 값을 조용히 내놓는다.
      → ensure_min_size() 로 반드시 확대해서 넣는다.
   2) 평면 일러스트는 안 된다.
      MediaPipe 는 실제 손 사진으로 학습된 모델이다. 음영도 질감도 없는
      벡터 그림에서는 확대해도 관절 위치가 신뢰할 수 없다.
      → 합격/불합격 판정에는 **실사진만** 쓴다.
        일러스트는 참고 표시만 하고 판정에서 제외한다.

■ 사용법
     python3 tests/제스처_검증.py                 (사진 자동 내려받기 포함)
     python3 tests/제스처_검증.py --no-download   (이미 받아둔 사진만 사용)

■ 시험 사진의 저작권
   아래 목록의 사진은 전부 **위키미디어 공용(Wikimedia Commons)** 의 자유 이용 저작물이며,
   각 항목에 **저작자와 라이선스**를 함께 적어 두었습니다.
   CC BY-SA 계열은 저작자 표시가 의무입니다.

   이 저장소는 **어떤 이미지 파일도 포함하지 않습니다.** 이 스크립트가 실행될 때
   각 배포처에서 내려받으며, 내려받은 파일도 저장소에 커밋하지 않습니다(.gitignore).
   전체 목록과 출처 링크는 저장소 최상위 `저작권_출처.md` 를 보십시오.

   변경 사항 고지 — 움직이는 GIF 는 첫 장만 추출하고, 형식을 PNG 로 바꾸며,
   짧은 변이 320픽셀 미만이면 확대해서 사용합니다.
================================================================================
"""

import argparse
import os
import sys
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))

from hand_tracking_control import (          # noqa: E402
    FINGER_NAMES, Calibrator, HandTracker, compute_raw_angles,
    landmarks_to_array, find_model, ensure_min_size, DEFAULT_MIN_SIZE,
)

IMG_DIR = os.path.join(_HERE, "..", "결과", "시험사진")
_FP = "https://commons.wikimedia.org/wiki/Special:FilePath/"

# ─────────────────────────────────────────────────────────────────────────────
# 판정용 자료 — 전부 실제 사진, 전부 위키미디어 공용의 자유 이용 저작물
#   (파일명, 원본 파일명, 설명, 펴야 하는 손가락, 굽혀야 하는 손가락, 라이선스)
# ─────────────────────────────────────────────────────────────────────────────
PHOTOS = [
    # (파일명, 위키미디어 원본 파일명, 설명, 펴야 하는 손가락, 굽혀야 하는 손가락,
    #  저작자, 라이선스)
    ("08_손펴기_실사진.png", "Open Palm of the Left Hand, Fingers.jpg",
     "손 펴기(보)", ["검지", "중지", "약지", "소지"], [],
     "Eyefive45", "CC BY-SA 4.0"),
    ("15_바위_가위바위보.png", "Rock-paper-scissors (rock).png",
     "주먹(바위)", [], ["검지", "중지", "약지", "소지"],
     "Sertion", "CC BY-SA 3.0"),
    ("14_브이_실사진.png", "Little girl giving V-sign in the sunshine in Laos.jpg",
     "브이(가위)", ["검지", "중지"], ["약지", "소지"],
     "Basile Morin", "CC BY-SA 4.0"),
    ("09_엄지척_실사진.png", "Thumb up.JPG",
     "엄지 척", ["엄지"], ["검지", "중지", "약지", "소지"],
     "Pogrebnoj-Alexandroff", "CC BY-SA 3.0"),
    ("10_OK_실사진.png", "OK Hand Gesture.jpg",
     "OK 사인", ["중지", "약지", "소지"], ["검지"],
     "faceofwiki", "CC0"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 참고용 자료 — 평면 일러스트(원본 25x75). 판정에는 쓰지 않는다. 위 ■ 항목 참조.
# ─────────────────────────────────────────────────────────────────────────────
ILLUSTS = [
    # (파일명, 위키미디어 원본 파일명, 설명, 저작자, 라이선스)
    ("01_손펴기.png", "Hand Gesture - Open Palm.gif", "손 펴기(일러스트)",
     "VideoPlasty", "CC BY-SA 4.0"),
    ("02_주먹.png", "Hand Gesture - Closed Fist.gif", "주먹(일러스트)",
     "VideoPlasty", "CC BY-SA 4.0"),
    ("03_브이.png", "Hand Gesture - Peace Sign.gif", "브이(일러스트)",
     "VideoPlasty", "CC BY-SA 4.0"),
    ("05_가리키기.png", "Hand Gesture - One.gif", "가리키기(일러스트)",
     "VideoPlasty", "CC BY-SA 4.0"),
    ("07_OK.png", "Hand Gesture - Ok.gif", "OK 사인(일러스트)",
     "VideoPlasty", "CC BY-SA 4.0"),
]

# ─────────────────────────────────────────────────────────────────────────────
# ★ 검출 한계 사례 — MediaPipe 가 손을 아예 찾지 못하는 실제 사진들.
#   실패가 아니라 '알아 두어야 할 한계'다. 로봇을 다룰 때 직접 영향이 있다:
#   추종 중에 이런 자세가 되면 손을 놓치므로, --relax-timeout 이 동작해
#   일정 시간 뒤 로봇 손이 스스로 펴진다.
#   (파일명, 원본 파일명, 설명, 못 찾는 이유, 라이선스)
# ─────────────────────────────────────────────────────────────────────────────
LIMITS = [
    # (파일명, 위키미디어 원본 파일명, 설명, 못 찾는 이유, 저작자, 라이선스)
    ("11_주먹_실사진.png", "Clenched fist.jpg", "주먹을 카메라 정면으로",
     "손가락 구조가 하나도 안 보인다. 신뢰도를 0.05 까지 낮춰도 못 찾는다",
     "Genusfotografen (Tomas Gunnarsson) / Wikimedia Sverige", "CC BY-SA 4.0"),
    ("12_가리키기_실사진.png", "The Big Index Finger - Flickr - mikecogh.jpg", "석조 조각상 손",
     "사람 손이 아니다. 모델이 사람 손으로 학습되었다",
     "Michael Coghlan from Adelaide, Australia", "CC BY-SA 2.0"),
    ("13_록사인_실사진.png", "Index and little fingers open.JPG", "흰 배경 과도한 접사",
     "손목·손등 맥락이 잘려 손바닥 검출기가 후보를 못 만든다",
     "Pogrebnoj-Alexandroff", "CC BY-SA 3.0"),
    ("16_록사인_현장.png", "Rock Horns Disturbed.jpg", "공연장 뿔 손동작",
     "손이 화면에서 너무 작고 조명이 어둡다",
     "Tom dl", "CC0"),
]


def fetch(fname, wiki_name, width=900):
    """위키미디어 공용에서 한 장 받아 PNG 로 저장한다."""
    from PIL import Image
    import io
    dst = os.path.join(IMG_DIR, fname)
    if os.path.exists(dst):
        return True
    url = _FP + urllib.parse.quote(wiki_name) + f"?width={width}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "BrainCo-Revo2-handtrack-verify/1.0"})
            data = urllib.request.urlopen(req, timeout=60).read()
            im = Image.open(io.BytesIO(data))
            im.seek(0)                        # 움직이는 GIF 는 첫 장만
            im.convert("RGB").save(dst)
            print(f"  받음  {fname:<24} [{wiki_name[:40]}]")
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:                 # 위키미디어 요청 과다 제한
                wait = 15 * (attempt + 1)
                print(f"  대기  {fname:<24} 요청 과다(429) — {wait}초 후 재시도")
                time.sleep(wait)
                continue
            print(f"  실패  {fname:<24} HTTP {e.code}")
            return False
        except Exception as e:
            print(f"  실패  {fname:<24} {type(e).__name__}: {e}")
            return False
    return False


def download_all():
    import urllib.parse  # noqa: F401  (fetch 안에서 사용)
    os.makedirs(IMG_DIR, exist_ok=True)
    for fname, wiki, *_ in PHOTOS:
        if fetch(fname, wiki):
            time.sleep(4)                     # 위키미디어에 대한 예의이자 429 회피
    for fname, wiki, *_ in ILLUSTS:
        if fetch(fname, wiki):
            time.sleep(4)
    for fname, wiki, *_ in LIMITS:
        if fetch(fname, wiki):
            time.sleep(4)


def measure(tracker, path, geom, min_size, thumb_aux):
    """사진 한 장에서 손가락 6칸 값을 뽑는다. 검출 실패면 None."""
    import cv2
    img = cv2.imread(path)
    if img is None:
        return None, "읽기실패"
    img, _up = ensure_min_size(img, min_size)     # 저해상도 함정 방지
    res = tracker.detect(img, 0)
    if not res.hand_landmarks:
        return None, "미검출"
    h, w = img.shape[:2]
    if geom == "world" and getattr(res, "hand_world_landmarks", None):
        pts = landmarks_to_array(res.hand_world_landmarks[0], use_z=True)
    else:
        pts = landmarks_to_array(res.hand_landmarks[0], use_z=(geom == "screen3d"))
        pts[:, 0] *= w
        pts[:, 1] *= h
        if geom == "screen3d":
            pts[:, 2] *= w
    ang = compute_raw_angles(pts)
    return Calibrator(adaptive=False).compose(ang, thumb_aux), None


def main():
    ap = argparse.ArgumentParser(description="제스처 의미 검증")
    ap.add_argument("--no-download", action="store_true", help="내려받기 생략")
    ap.add_argument("--model", default=None)
    ap.add_argument("--geom", default="screen2d",
                    choices=["screen2d", "screen3d", "world"])
    ap.add_argument("--margin", type=int, default=100,
                    help="'폄'과 '쥠' 평균이 이만큼 이상 벌어져야 통과")
    ap.add_argument("--thumb-aux", default="follow",
                    choices=["follow", "geom", "fixed"])
    ap.add_argument("--min-size", type=int, default=DEFAULT_MIN_SIZE)
    args = ap.parse_args()

    print("=" * 82)
    print(" 제스처 의미 검증 — 정답을 아는 손동작 사진으로 위치값이 맞는지 확인")
    print("=" * 82)

    if not args.no_download:
        print("\n[1] 시험 사진 준비 (위키미디어 공용, 자유 이용 저작물)")
        download_all()

    model = find_model(args.model)
    tracker = HandTracker(model, num_hands=1, det_conf=0.3, pres_conf=0.3,
                          video_mode=False)

    print(f"\n[2] 판정 — 실제 사진만 사용 (좌표={args.geom}, 판정여유={args.margin},"
          f" 최소해상도={args.min_size})\n")
    head = f"  {'제스처':<20}" + "".join(f"{n:>7}" for n in FINGER_NAMES) + "   판정"
    print(head)
    print("  " + "-" * (len(head) + 6))

    n_pass = n_fail = n_skip = 0
    for fname, _wiki, desc, open_f, curl_f, _artist, _lic in PHOTOS:
        path = os.path.join(IMG_DIR, fname)
        if not os.path.exists(path):
            print(f"  {desc:<20}{'파일없음':<10}")
            n_skip += 1
            continue
        pos, err = measure(tracker, path, args.geom, args.min_size, args.thumb_aux)
        if pos is None:
            print(f"  {desc:<20}{err:<10}")
            n_skip += 1
            continue
        d = dict(zip(FINGER_NAMES, pos))

        if open_f and curl_f:
            a = sum(d[n] for n in open_f) / len(open_f)
            b = sum(d[n] for n in curl_f) / len(curl_f)
            ok = (b - a) >= args.margin
            note = f"폄{a:.0f} < 쥠{b:.0f}"
        elif open_f:
            a = sum(d[n] for n in open_f) / len(open_f)
            ok = a < 400
            note = f"폄평균 {a:.0f} < 400"
        else:
            b = sum(d[n] for n in curl_f) / len(curl_f)
            ok = b > 600
            note = f"쥠평균 {b:.0f} > 600"

        n_pass += int(ok)
        n_fail += int(not ok)
        print(f"  {desc:<20}" + "".join(f"{v:>7}" for v in pos)
              + f"   {'통과' if ok else '실패'}  {note}")

    print("\n[3] 참고 — 평면 일러스트 (원본 25x75). 판정에서 제외한다.")
    print("     MediaPipe 는 실제 손 사진으로 학습된 모델이라, 음영도 질감도 없는")
    print("     벡터 그림에서는 확대해도 관절 위치를 신뢰할 수 없다.\n")
    for fname, _wiki, desc, _artist, _lic in ILLUSTS:
        path = os.path.join(IMG_DIR, fname)
        if not os.path.exists(path):
            print(f"  {desc:<20}{'파일없음':<10}")
            continue
        pos, err = measure(tracker, path, args.geom, args.min_size, args.thumb_aux)
        if pos is None:
            print(f"  {desc:<20}{err:<10}")
            continue
        print(f"  {desc:<20}" + "".join(f"{v:>7}" for v in pos) + "   (참고)")

    print("\n[4] 검출 한계 사례 — 손을 아예 못 찾는 실제 사진. 실패가 아니라 한계다.")
    print("     추종 중 이런 자세가 되면 로봇은 마지막 자세를 유지하다가")
    print("     --relax-timeout 초 뒤 스스로 손을 편다(안전 동작).\n")
    for fname, _wiki, desc, why, _artist, _lic in LIMITS:
        path = os.path.join(IMG_DIR, fname)
        if not os.path.exists(path):
            print(f"  {desc:<20}{'파일없음':<10}")
            continue
        pos, err = measure(tracker, path, args.geom, args.min_size, args.thumb_aux)
        state = "검출됨(예상 밖)" if pos is not None else (err or "미검출")
        print(f"  {desc:<20}{state:<16} {why}")

    tracker.close()
    print("\n" + "=" * 82)
    print(f" 결과: 통과 {n_pass}건 / 실패 {n_fail}건 / 건너뜀 {n_skip}건"
          f"   (판정 대상은 실사진 {len(PHOTOS)}건)")
    print("=" * 82)
    return 0 if (n_fail == 0 and n_pass > 0) else 1


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
