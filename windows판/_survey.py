#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_survey.py — 이 컴퓨터를 통째로 조사해서, 로봇손이 어디에 붙었는지 찾아낸다.

★왜 필요한가 (2026-09-10 j2w 요청)
  「포트가 없다」는 말만으로는 사람이 무엇을 고칠지 알 수 없다. 같은 로봇을
  다른 PC 에 꽂으니 COM 이 하나도 안 잡혔는데, 원인이 케이블인지 전원인지
  드라이버인지 구분이 안 됐다.
  그래서 **USB 버스 수준까지 내려가** 장치를 VID/PID 로 식별한다.
      · COM 이 생겼다            → 바로 쓴다
      · USB 로는 보이는데 COM 이 없다 → **드라이버만 깔면 된다** (어느 것인지도 안다)
      · USB 에도 없다            → 케이블·전원·포트 문제
  이 셋은 해야 할 일이 전혀 다르다. 구분해 주지 않으면 사람이 헤맨다.

결과는 JSON 한 줄(<<<SURVEY>>> 로 시작)로 찍는다. _setup.py 가 읽는다.
"""
import json
import os
import platform
import subprocess
import sys

MARK = "<<<SURVEY>>>"
IS_WINDOWS = (os.name == "nt")

# USB-직렬 변환 칩 — 이 칩이 보이면 COM 포트가 생겨야 정상이다.
#   로봇손·아두이노·각종 장비가 이 칩으로 PC 와 통신한다.
USB_SERIAL_CHIPS = {
    # BrainCo Revo2 로봇손이 쓰는 칩 (2026-09-10 실측으로 확인)
    "0403:6015": ("FTDI FT231X USB UART  ← BrainCo Revo2 로봇손", "FTDI VCP",
                  "https://ftdichip.com/drivers/vcp-drivers/"),
    "0403": ("FTDI (FT232·FT231 계열)", "FTDI VCP",
             "https://ftdichip.com/drivers/vcp-drivers/"),
    "10C4": ("Silicon Labs CP210x", "CP210x",
             "https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers"),
    "1A86:7523": ("QinHeng CH340 (가장 흔함)", "CH340",
                  "https://www.wch-ic.com/downloads/CH341SER_EXE.html"),
    "1A86": ("QinHeng CH340/CH341", "CH340",
             "https://www.wch-ic.com/downloads/CH341SER_EXE.html"),
    "067B": ("Prolific PL2303", "PL2303",
             "https://www.prolific.com.tw/US/ShowProduct.aspx?p_id=225&pcid=41"),
}


def ps(cmd, timeout=60):
    """PowerShell 한 줄을 돌려 문자열을 돌려준다."""
    if not IS_WINDOWS:
        return ""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace")
        return (r.stdout or "").strip()
    except Exception:
        return ""


def ps_json(cmd, timeout=60):
    txt = ps(cmd, timeout)
    if not txt:
        return []
    try:
        d = json.loads(txt)
    except Exception:
        return []
    return d if isinstance(d, list) else [d]


def 기본정보():
    out = {
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "python_bits": 64 if sys.maxsize.bit_length() >= 63 else 32,
        "cwd": os.getcwd(),
    }
    if IS_WINDOWS:
        cs = ps_json("Get-CimInstance Win32_ComputerSystem | "
                     "Select-Object Manufacturer,Model,TotalPhysicalMemory | "
                     "ConvertTo-Json -Compress")
        cpu = ps_json("Get-CimInstance Win32_Processor | "
                      "Select-Object Name,NumberOfCores | ConvertTo-Json -Compress")
        gpu = ps_json("Get-CimInstance Win32_VideoController | "
                      "Select-Object Name,DriverVersion | ConvertTo-Json -Compress")
        os_ = ps_json("Get-CimInstance Win32_OperatingSystem | "
                      "Select-Object Caption,Version,OSArchitecture | "
                      "ConvertTo-Json -Compress")
        out["computer"] = cs[0] if cs else {}
        out["cpu"] = cpu[0] if cpu else {}
        out["gpu"] = gpu
        out["os_detail"] = os_[0] if os_ else {}
    return out


def com_포트들():
    """장치 관리자의 포트(COM & LPT) 항목."""
    if not IS_WINDOWS:
        return []
    return ps_json("$ErrorActionPreference='SilentlyContinue';"
                   "Get-PnpDevice -Class Ports -PresentOnly | "
                   "Select-Object Status,FriendlyName,InstanceId | "
                   "ConvertTo-Json -Compress")


def usb_장치들():
    """USB 버스에 보이는 장치 전부 (드라이버가 없어도 여기엔 나온다)."""
    if not IS_WINDOWS:
        return []
    return ps_json("$ErrorActionPreference='SilentlyContinue';"
                   "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB*' } | "
                   "Select-Object Status,Class,FriendlyName,InstanceId | "
                   "ConvertTo-Json -Compress", timeout=90)


def 문제장치들():
    if not IS_WINDOWS:
        return []
    return ps_json("$ErrorActionPreference='SilentlyContinue';"
                   "Get-PnpDevice -PresentOnly | Where-Object { $_.Status -ne 'OK' } | "
                   "Select-Object Status,Class,FriendlyName,InstanceId,Problem | "
                   "ConvertTo-Json -Compress")


def vid_pid(instance_id):
    """USB\\VID_10C4&PID_EA60\\... 에서 (VID, PID) 를 뽑는다."""
    s = (instance_id or "").upper()
    vid = pid = ""
    if "VID_" in s:
        vid = s.split("VID_", 1)[1][:4]
    if "PID_" in s:
        pid = s.split("PID_", 1)[1][:4]
    return vid, pid


def pyserial_포트들():
    try:
        from serial.tools import list_ports
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    out = []
    for p in list_ports.comports():
        out.append({"device": p.device, "desc": p.description or "",
                    "hwid": p.hwid or "", "vid": f"{p.vid:04X}" if p.vid else "",
                    "pid": f"{p.pid:04X}" if p.pid else "",
                    "manufacturer": p.manufacturer or ""})
    return out, ""


def sdk_포트들(sdk):
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
        out.append(it.get("port_name") or it.get("name") or it.get("port")
                   or str(it) if isinstance(it, dict) else str(it))
    return out, ""


def 카메라들():
    try:
        import cv2
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if IS_WINDOWS:
        backends = [(cv2.CAP_DSHOW, "DirectShow"), (cv2.CAP_MSMF, "MediaFoundation"),
                    (cv2.CAP_ANY, "자동")]
    else:
        backends = [(cv2.CAP_V4L2, "V4L2")]
    found = []
    for idx in range(8):
        for be, name in backends:
            try:
                cap = cv2.VideoCapture(idx, be)
            except Exception:
                continue
            if not cap.isOpened():
                cap.release()
                continue
            ok, fr = cap.read()
            if ok and fr is not None:
                found.append({"index": idx, "backend": name,
                              "w": int(fr.shape[1]), "h": int(fr.shape[0])})
                cap.release()
                break
            cap.release()
    return found, ""


def 직렬칩찾기(결과):
    """지금 꽂혀 있는 USB 장치 중 직렬 변환 칩을 골라낸다."""
    후보 = []
    for d in (결과.get("usb_devices") or []):
        vid, pid = vid_pid(d.get("InstanceId"))
        정보 = USB_SERIAL_CHIPS.get(f"{vid}:{pid}") or USB_SERIAL_CHIPS.get(vid)
        if 정보:
            후보.append({"이름": d.get("FriendlyName"), "상태": d.get("Status"),
                         "vid": vid, "pid": pid, "칩": 정보[0],
                         "드라이버": 정보[1], "링크": 정보[2],
                         "instance": d.get("InstanceId")})
    return 후보


def 판정(결과):
    """조사 결과를 보고 「무엇을 해야 하는가」를 정한다."""
    sdk = 결과.get("sdk_ports") or []
    ser = 결과.get("serial_ports") or []
    usb = 결과.get("usb_devices") or []
    문제 = 결과.get("problem_devices") or []

    usb_ser = [p for p in ser
               if ("USB" in (p.get("hwid", "")).upper() or p.get("vid"))
               and "BLUETOOTH" not in (p.get("desc", "")).upper()]

    # ① 바로 쓸 수 있는 포트가 있는가
    쓸포트 = list(sdk) or [p["device"] for p in usb_ser]
    if 쓸포트:
        return {"상태": "준비됨", "포트": 쓸포트,
                "말": f"쓸 수 있는 포트를 찾았습니다: {', '.join(쓸포트)}"}

    # ② USB 로는 보이는데 COM 이 없는가 → 드라이버 문제
    후보 = 결과.get("serial_chips") or []
    if 후보:
        return {"상태": "드라이버필요", "후보": 후보,
                "말": "USB 로는 보이는데 COM 포트가 만들어지지 않았습니다. "
                      "직렬 변환 칩의 드라이버를 설치하면 됩니다."}

    # ③ 상태가 나쁜 장치 중 직렬로 보이는 것
    의심 = [d for d in 문제
            if any(k in (d.get("FriendlyName") or "").upper()
                   for k in ("SERIAL", "UART", "CH34", "CP21", "FT23", "USB"))]
    if 의심:
        return {"상태": "장치이상", "의심": 의심,
                "말": "드라이버가 없거나 오류인 장치가 있습니다. "
                      "장치 관리자에서 노란 느낌표를 확인하십시오."}

    return {"상태": "장치없음",
            "말": "USB 버스에서 직렬 변환 장치를 찾지 못했습니다. "
                  "케이블·USB 포트·전원을 확인하십시오."}


def main():
    sdk = sys.argv[1] if len(sys.argv) > 1 else ""
    결과 = {"ok": True}
    결과.update(기본정보())

    s, serr = sdk_포트들(sdk)
    결과["sdk_ports"] = s or []
    결과["sdk_error"] = serr

    ps_, perr = pyserial_포트들()
    결과["serial_ports"] = ps_ or []
    결과["serial_error"] = perr

    결과["com_devices"] = com_포트들()
    결과["usb_devices"] = usb_장치들()
    결과["problem_devices"] = 문제장치들()

    cams, cerr = 카메라들()
    결과["cameras"] = cams or []
    결과["camera_error"] = cerr

    결과["serial_chips"] = 직렬칩찾기(결과)
    결과["판정"] = 판정(결과)
    print(MARK + json.dumps(결과, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
