#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_ports.py — 로봇손이 붙을 수 있는 직렬 포트를 여러 방법으로 찾아 JSON 으로 찍는다.

★한 가지 방법만 보면 안 된다 (2026-09-10 두 번째 윈도우 PC 에서 겪음)
  제조사 SDK 의 list_available_ports() 가 빈 목록을 주면 「로봇이 없다」로
  보이지만, 실제로는 **윈도우가 장치를 알고 있는데 드라이버가 없거나**
  SDK 가 그 칩을 못 알아보는 경우가 있다. 그러면 사람은 무엇을 고쳐야
  할지 알 수 없다. 그래서 세 가지로 나눠 본다.
      ① 제조사 SDK 가 아는 포트
      ② pyserial 이 아는 COM 포트 (윈도우 등록 정보 그대로)
      ③ 윈도우가 아는 USB 장치 중 문제 있는 것 (드라이버 없음 등)
"""
import json
import os
import subprocess
import sys

MARK = "<<<PORTS>>>"
IS_WINDOWS = (os.name == "nt")


def sdk_ports(sdk):
    revo2 = os.path.join(sdk, "python", "revo2")
    if os.path.isdir(revo2) and revo2 not in sys.path:
        sys.path.insert(0, revo2)
    try:
        from revo2_utils import libstark
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    try:
        raw = libstark.list_available_ports()
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        items = json.loads(text)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    out = []
    for it in items:
        if isinstance(it, dict):
            out.append(it.get("port_name") or it.get("name") or it.get("port")
                       or it.get("device") or str(it))
        else:
            out.append(str(it))
    return out, ""


def serial_ports():
    """pyserial 이 아는 포트. 윈도우 등록 정보를 그대로 읽으므로 SDK 보다 넓다."""
    try:
        from serial.tools import list_ports
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    out = []
    for p in list_ports.comports():
        out.append({"device": p.device, "desc": p.description or "",
                    "hwid": p.hwid or "", "manufacturer": p.manufacturer or ""})
    return out, ""


def windows_usb_problems():
    """윈도우가 아는 장치 중 상태가 정상이 아닌 것 (드라이버 없음 등)."""
    if not IS_WINDOWS:
        return [], ""
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "Get-PnpDevice | Where-Object { $_.Status -ne 'OK' } |"
        "Select-Object -First 20 Status,Class,FriendlyName,InstanceId |"
        "ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", ps],
                           capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"
    txt = (r.stdout or "").strip()
    if not txt:
        return [], ""
    try:
        d = json.loads(txt)
    except Exception:
        return [], txt[:300]
    return (d if isinstance(d, list) else [d]), ""


def windows_com_devices():
    """윈도우가 아는 COM 포트 전체 (장치 관리자 → 포트 와 같은 목록)."""
    if not IS_WINDOWS:
        return [], ""
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "Get-PnpDevice -Class Ports |"
        "Select-Object Status,FriendlyName,InstanceId |"
        "ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", ps],
                           capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"
    txt = (r.stdout or "").strip()
    if not txt:
        return [], ""
    try:
        d = json.loads(txt)
    except Exception:
        return [], txt[:300]
    return (d if isinstance(d, list) else [d]), ""


def main():
    sdk = sys.argv[1] if len(sys.argv) > 1 else ""
    결과 = {"ok": True}

    s, serr = sdk_ports(sdk)
    결과["sdk_ports"] = s if s is not None else []
    결과["sdk_error"] = serr

    ps_, perr = serial_ports()
    결과["serial_ports"] = ps_ if ps_ is not None else []
    결과["serial_error"] = perr

    com, cerr = windows_com_devices()
    결과["win_com"] = com
    결과["win_com_error"] = cerr

    bad, berr = windows_usb_problems()
    결과["win_problem"] = bad
    결과["win_problem_error"] = berr

    # ── 자동으로 쓸 포트를 고른다 ──────────────────────────────────────
    # ★pyserial 목록을 그대로 쓰면 안 된다 (2026-09-10 실측)
    #   리눅스는 실제로 없는 내장 포트 /dev/ttyS0~31 을 32개나 보고하고,
    #   윈도우는 블루투스 가상 COM 이 섞인다. 그것을 로봇으로 착각하면
    #   엉뚱한 포트에 연결을 시도하다 실패한다.
    #   그래서 **USB 로 보이는 것만** 후보로 삼는다.
    def usb로보이나(it):
        h = (it.get("hwid") or "").upper()
        d = (it.get("desc") or "").upper()
        m = (it.get("manufacturer") or "").upper()
        if "BLUETOOTH" in d or "BLUETOOTH" in h:
            return False
        return ("USB" in h) or ("VID:" in h) or ("USB" in d) or ("USB" in m)

    usb후보 = [p["device"] for p in 결과["serial_ports"] if usb로보이나(p)]
    결과["usb_serial"] = usb후보

    쓸것 = list(결과["sdk_ports"])          # ① 제조사 SDK 가 아는 것이 가장 확실하다
    if not 쓸것:
        쓸것 = usb후보                       # ② 없으면 USB 로 보이는 것만
    결과["ports"] = 쓸것

    print(MARK + json.dumps(결과, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
