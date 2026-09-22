#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조사 결과에 따라 프로그램이 스스로 맞추는지 검사한다 (장비 없이).

★2026-09-10 j2w 상황을 그대로 재현한다: 카메라는 잡히는데 포트가 없다.
  그때 「없다」로 끝내지 않고 **왜 없는지**를 가려내는지 본다.
"""
import builtins, contextlib, importlib.util, io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("setup_mod", os.path.join(HERE, "_setup.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.LOGF = "/tmp/_시험기록2.txt"
m.SURVEY_TXT = "/tmp/_시험조사.txt"

P = F = 0
def ok(t):
    global P; P += 1; print(f"  \033[32m✓\033[0m {t}")
def ng(t):
    global F; F += 1; print(f"  \033[31m✗\033[0m {t}")

CAM = [{"index": 0, "w": 640, "h": 480, "backend": "DirectShow"}]

def 조사를(판정, cams=CAM, **extra):
    d = {"os": "Windows-10", "python": "3.12.10", "python_bits": 64,
         "computer": {"Manufacturer": "ASUS", "Model": "X570",
                      "TotalPhysicalMemory": 34359738368},
         "cpu": {"Name": "AMD Ryzen 7"}, "gpu": [{"Name": "GeForce RTX 2060"}],
         "os_detail": {"Caption": "Windows 10 Pro", "OSArchitecture": "64비트"},
         "cameras": cams, "camera_error": "",
         "sdk_ports": [], "sdk_error": "", "serial_ports": [], "serial_error": "",
         "com_devices": [], "usb_devices": [], "problem_devices": [],
         "판정": 판정}
    d.update(extra)
    m.run_survey = lambda vpy: (True, d, "")
    return d

def 실행(mode="robot", passthrough=(), 입력=None):
    """입력=None 이면 이미 설정된 input 을 그대로 쓴다.
    ★여기서 무조건 input 을 덮으면, 앞에서 준비한 답(동의 y 등)이 지워져
      시험이 엉뚱한 이유로 실패한다 (2026-09-10 실제로 그랬다)."""
    buf = io.StringIO()
    if 입력 is not None:
        it = iter(입력)
        builtins.input = lambda *a, **k: next(it, "")
    m.run_and_log = lambda cmd, env: (0, print(f"[실행됨] {' '.join(cmd[-6:])}"))[0]
    with contextlib.redirect_stdout(buf):
        try:
            rc = m.run_body("py", mode, list(passthrough))
        except SystemExit as e:
            rc = e.code
    return rc, buf.getvalue()

print("\n1. 쓸 포트가 있으면 그것으로 바로 실행한다")
조사를({"상태": "준비됨", "포트": ["COM3"], "말": "찾았습니다"})
rc, out = 실행(입력=[""])
ok("COM3 를 골랐다") if "로봇손 포트 COM3" in out else ng("포트를 못 골랐다")
ok("카메라도 조사 결과에서 가져왔다") if "카메라 0번" in out else ng("카메라를 다시 물었다")
ok("--port COM3 로 실행했다") if "--port COM3" in out else ng(f"실행 인자가 이상하다")

print("\n2. ★j2w 상황 — 카메라는 있고 포트가 없다 (드라이버 문제)")
조사를({"상태": "드라이버필요",
       "후보": [{"이름": "USB-SERIAL CH340", "상태": "Error", "vid": "1A86",
                "pid": "7523", "칩": "QinHeng CH340/CH341", "드라이버": "CH340",
                "링크": "https://www.wch-ic.com/downloads/CH341SER_EXE.html",
                "instance": "USB\\VID_1A86&PID_7523\\5&1"}],
       "말": "USB 로는 보이는데 COM 포트가 만들어지지 않았습니다."},
      usb_devices=[{"Status": "Error", "Class": "", "FriendlyName": "USB-SERIAL CH340",
                    "InstanceId": "USB\\VID_1A86&PID_7523\\5&1"}])
rc, out = 실행(입력=[""])
ok("실행하지 않고 멈춘다") if rc == 1 and "[실행됨]" not in out else ng("그냥 실행했다")
ok("무엇이 문제인지 말한다") if "드라이버필요" in out else ng("판정이 안 보인다")
ok("어느 칩인지 알려 준다") if "CH340" in out else ng("칩 정보가 없다")
ok("VID/PID 를 보여 준다") if "1A86" in out and "7523" in out else ng("VID/PID 가 없다")
ok("드라이버 받는 곳을 알려 준다") if "wch-ic.com" in out else ng("링크가 없다")
ok("컴퓨터 사양도 함께 보여 준다") if "RTX 2060" in out else ng("사양이 안 보인다")

print("\n3. USB 에도 없으면 케이블·전원을 짚어 준다")
조사를({"상태": "장치없음", "말": "USB 버스에서 직렬 변환 장치를 찾지 못했습니다."})
rc, out = 실행(입력=[""])
ok("실행하지 않는다") if rc == 1 and "[실행됨]" not in out else ng("그냥 실행했다")
ok("케이블·전원을 짚는다") if "24V" in out and "케이블" in out else ng("안내가 없다")
ok("충전 전용 케이블 가능성도 짚는다") if "충전 전용" in out else ng("그 안내가 없다")

print("\n4. 상태가 이상한 장치가 있으면 장치 관리자로 보낸다")
조사를({"상태": "장치이상",
       "의심": [{"Status": "Error", "FriendlyName": "USB Serial Device"}],
       "말": "드라이버가 없거나 오류인 장치가 있습니다."})
rc, out = 실행(입력=[""])
ok("장치 관리자를 안내한다") if "장치 관리자" in out else ng("안내가 없다")

print("\n5. 사람이 --port 를 직접 주면 조사를 건너뛰고 그것을 쓴다")
불림 = {"v": False}
def 조사흔적(vpy):
    불림["v"] = True
    return True, {"cameras": CAM, "판정": {"상태": "준비됨", "포트": ["COM9"]}}, ""
m.run_survey = 조사흔적
rc, out = 실행(passthrough=["--port", "COM5", "--source", "0"], 입력=[""])
ok("지정한 COM5 를 쓴다") if "COM5" in out else ng("지정을 무시했다")
ok("둘 다 지정하면 조사하지 않는다") if not 불림["v"] else ng("불필요하게 조사했다")

print("\n6. 조사 결과를 파일로 남긴다 (보내 달라고 할 수 있게)")
조사를({"상태": "장치없음", "말": "없음"})
rc, out = 실행(입력=[""])
ok("환경조사.txt 를 저장한다") if os.path.exists(m.SURVEY_TXT) else ng("파일이 없다")
ok("보내 달라고 안내한다") if "보내 주시면" in out else ng("안내가 없다")


# ─────────────────────────────────────────────────────────────────────────
#  드라이버 자동 설치 (2026-09-10 추가)
#  j2w PC 의 실제 상황: FTDI FT231X 가 Error 상태로 꽂혀 있다
# ─────────────────────────────────────────────────────────────────────────
FTDI후보 = [{"이름": "FT231X USB UART", "상태": "Error", "vid": "0403", "pid": "6015",
            "칩": "FTDI FT231X USB UART  ← BrainCo Revo2 로봇손",
            "드라이버": "FTDI VCP", "링크": "https://ftdichip.com/drivers/vcp-drivers/",
            "instance": "USB\\VID_0403&PID_6015\\DU0D96T1"}]
드라이버필요 = {"상태": "드라이버필요", "후보": FTDI후보,
            "말": "USB 로는 보이는데 COM 포트가 만들어지지 않았습니다."}

def 설치기를(결과, 기록=None):
    def 가짜(cmd, env=None, capture_output=None, text=None, timeout=None,
            encoding=None, errors=None):
        if 기록 is not None:
            기록.append(cmd)
        class R: pass
        r = R(); r.stdout = "<<<DRIVER>>>" + json.dumps(결과, ensure_ascii=False)
        r.stderr = ""; r.returncode = 0
        return r
    m.subprocess.run = 가짜

import json
print("\n7. 드라이버가 필요하면 설치를 제안한다")
조사를(드라이버필요)
입력들 = iter(["n"])
builtins.input = lambda *a, **k: next(입력들, "")
rc, out = 실행()
ok("설치할지 물어본다") if "설치하시겠습니까" in out else ng("묻지 않는다")
ok("어떤 칩인지 보여 준다") if "FT231X" in out and "0403" in out else ng("칩 정보가 없다")
ok("관리자 권한 창이 뜬다고 미리 알린다") if "관리자 권한 창" in out else ng("UAC 안내가 없다")
ok("권한이 왜 필요한지 설명한다") if "시스템에 등록" in out else ng("이유 설명이 없다")
ok("거절하면 설치하지 않는다") if "설치하지 않았습니다" in out else ng("거절을 무시했다")
ok("거절하면 실행도 하지 않는다") if rc == 1 and "[실행됨]" not in out else ng("그냥 실행했다")

print("\n8. 동의하면 설치하고, 성공하면 다시 살펴본 뒤 실행한다")
조사를(드라이버필요)
호출 = []
설치기를({"ok": True, "step": "windows_update", "message": "윈도우가 장치를 다시 확인했습니다."}, 호출)
상태들 = iter([  # 첫 조사는 드라이버필요, 설치 뒤 조사는 준비됨
    (True, {"cameras": CAM, "판정": 드라이버필요}, ""),
    (True, {"cameras": CAM, "판정": {"상태": "준비됨", "포트": ["COM7"]}}, ""),
])
m.run_survey = lambda vpy: next(상태들)
입력들 = iter(["y", "", ""])
builtins.input = lambda *a, **k: next(입력들, "")
rc, out = 실행()
ok("설치 도우미를 부른다") if any("_driver.py" in " ".join(c) for c in 호출) else ng("부르지 않았다")
ok("어떤 드라이버인지 넘긴다") if any("FTDI VCP" in " ".join(c) for c in 호출) else ng("인자가 없다")
ok("USB 를 다시 꽂으라고 안내한다") if "다시 꽂아" in out else ng("안내가 없다")
ok("설치 뒤 다시 살펴본다") if "다시 살펴봅니다" in out else ng("재조사가 없다")
ok("새로 생긴 포트로 진행한다") if "COM7" in out else ng("새 포트를 못 썼다")

print("\n9. 설치했는데도 포트가 안 생기면 정직하게 멈춘다")
호출 = []
설치기를({"ok": True, "step": "vendor_installer", "message": "설치 파일을 실행했습니다."}, 호출)
상태들 = iter([
    (True, {"cameras": CAM, "판정": 드라이버필요}, ""),
    (True, {"cameras": CAM, "판정": {"상태": "드라이버필요", "후보": FTDI후보,
                                    "말": "아직입니다"}}, ""),
])
m.run_survey = lambda vpy: next(상태들)
입력들 = iter(["y", "", ""])
builtins.input = lambda *a, **k: next(입력들, "")
rc, out = 실행()
ok("실행하지 않고 멈춘다") if rc == 1 and "[실행됨]" not in out else ng("그냥 실행했다")
ok("한 번 더 해 보라고 안내한다") if "한 번 더 실행" in out else ng("안내가 없다")

print("\n10. 설치 자체가 실패하면 받는 곳을 알려 준다")
설치기를({"ok": False, "step": "failed", "page": "https://ftdichip.com/drivers/vcp-drivers/",
        "error": "내려받지 못했습니다."})
조사를(드라이버필요)
입력들 = iter(["y", ""])
builtins.input = lambda *a, **k: next(입력들, "")
rc, out = 실행()
ok("실패를 알린다") if "설치하지 못했습니다" in out else ng("실패를 감췄다")
ok("받는 곳을 알려 준다") if "ftdichip.com" in out else ng("주소가 없다")

print(f"\n최종  통과 {P}건 · 실패 {F}건")
sys.exit(1 if F else 0)
