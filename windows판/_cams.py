#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_cams.py — 쓸 수 있는 카메라 번호만 JSON 으로 찍는다.

_setup.py 가 .venv 파이썬으로 불러 목록을 받아 온다.
★「열렸다」가 아니라 「한 장이 실제로 읽힌다」를 기준으로 삼는다.
  윈도우에는 열리기만 하고 영상이 안 나오는 장치가 흔하다.
"""
import json
import os
import sys

MARK = "<<<CAMS>>>"


def main():
    try:
        import cv2
    except Exception as e:
        print(MARK + json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"},
                                ensure_ascii=False))
        return 0

    is_win = (os.name == "nt")
    if is_win:
        backends = [(cv2.CAP_DSHOW, "DirectShow"),
                    (cv2.CAP_MSMF, "MediaFoundation"),
                    (cv2.CAP_ANY, "자동")]
    else:
        backends = [(cv2.CAP_V4L2, "V4L2")]

    found = []
    tried = []
    for idx in range(8):
        for be, name in backends:
            try:
                cap = cv2.VideoCapture(idx, be)
            except Exception:
                continue
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            ok, fr = cap.read()
            if ok and fr is not None:
                found.append({"index": idx, "backend": name,
                              "w": int(fr.shape[1]), "h": int(fr.shape[0])})
                cap.release()
                break
            tried.append(f"{idx}번/{name}: 열렸으나 영상 없음")
            cap.release()
    print(MARK + json.dumps({"ok": True, "cams": found, "tried": tried},
                            ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
