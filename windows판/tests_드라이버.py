#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""드라이버 설치 판정이 「종료코드」가 아니라 「실제 상태」를 보는지 검사한다.

★2026-09-10 실제 사고
  pnputil /scan-devices 는 드라이버가 시스템에 없으면 아무 일도 안 하는데
  **종료코드는 0** 이다. 그것을 성공으로 읽어 실제 설치로 넘어가지 않았다.
"""
import importlib.util, io, os, sys, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("drv", os.path.join(HERE, "_driver.py"))
drv = importlib.util.module_from_spec(spec); spec.loader.exec_module(drv)
drv.IS_WINDOWS = True     # 윈도우인 척한다 (판정 논리만 본다)

P = F = 0
def ok(t):
    global P; P += 1; print(f"  \033[32m✓\033[0m {t}")
def ng(t):
    global F; F += 1; print(f"  \033[31m✗\033[0m {t}")

print("\n1. 드라이버가 붙었는지 «상태»로 판정한다")
drv.ps_json = lambda cmd, timeout=60: (
    [{"Status": "Error", "FriendlyName": "FT231X USB UART"}] if "VID_0403" in cmd else [])
ok("장치가 Error 면 「안 붙음」") if not drv.드라이버붙었나() else ng("Error 인데 붙었다고 했다")

drv.ps_json = lambda cmd, timeout=60: (
    [{"Status": "OK", "FriendlyName": "USB Serial Port (COM7)"}] if "VID_0403" in cmd else [])
ok("장치가 OK 면 「붙음」") if drv.드라이버붙었나() else ng("OK 인데 안 붙었다고 했다")

# 상태를 못 읽어도 USB COM 포트가 있으면 붙은 것으로 본다
drv.ps_json = lambda cmd, timeout=60: (
    [] if "VID_0403" in cmd else [{"FriendlyName": "USB Serial Port (COM7)"}])
ok("상태를 못 읽어도 USB COM 이 생겼으면 붙음") if drv.드라이버붙었나() \
    else ng("COM 이 생겼는데 못 알아봤다")

drv.ps_json = lambda cmd, timeout=60: (
    [] if "VID_0403" in cmd else [{"FriendlyName": "통신 포트(COM1)"}])
ok("내장 COM1 만 있으면 붙지 않은 것") if not drv.드라이버붙었나() \
    else ng("COM1 을 로봇으로 착각했다")

print("\n2. ★pnputil 이 0 을 돌려줘도 장치가 그대로면 성공으로 치지 않는다")
drv.ps_runas = lambda exe, args, wait=True: (0, "")        # 종료코드 0 (성공처럼 보인다)
drv.ps_json = lambda cmd, timeout=60: (
    [{"Status": "Error", "FriendlyName": "FT231X USB UART"}] if "VID_0403" in cmd else [])
붙음, msg = drv.윈도우업데이트로시도()
ok("종료코드 0 이어도 「안 됐다」로 본다") if not 붙음 else ng("종료코드만 믿었다")
ok("종료코드를 기록에 남긴다") if "종료코드 0" in msg else ng("근거가 안 남았다")

print("\n3. 1단계가 안 되면 2단계(공식 설치 파일)로 넘어간다")
불림 = {"ftdi": False}
def 가짜설치():
    불림["ftdi"] = True
    return False, "내려받지 못했습니다"
drv.ftdi설치 = 가짜설치
drv.브라우저로열기 = lambda url: True
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    drv.main()
out = buf.getvalue()
ok("공식 설치 단계를 실제로 시도한다") if 불림["ftdi"] else ng("1단계에서 멈췄다")
ok("실패를 정직하게 보고한다") if '"ok": false' in out else ng("실패를 감췄다")
ok("받는 곳을 알려 준다") if "ftdichip.com" in out else ng("주소가 없다")

print("\n4. 설치 파일이 실행돼도 「붙었는지」 다시 확인한다")
drv.ftdi설치 = lambda: (True, "설치 파일을 실행했습니다")
drv.ps_json = lambda cmd, timeout=60: (
    [{"Status": "Error", "FriendlyName": "FT231X USB UART"}] if "VID_0403" in cmd else [])
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    drv.main()
out = buf.getvalue()
ok("실행했어도 안 붙었으면 그렇게 말한다") if '"installed": false' in out \
    else ng("실행만으로 성공이라 했다")
ok("USB 를 다시 꽂으라고 안내한다") if "다시 꽂아" in out else ng("안내가 없다")

print("\n5. 받은 파일을 검사한 뒤에만 실행한다")
import tempfile
d = tempfile.mkdtemp()
작은파일 = os.path.join(d, "a.zip")
open(작은파일, "wb").write(b"PK" + b"0" * 100)
res = drv.받은파일검사(작은파일)
ok("너무 작은 파일은 거부") if not res[0] else ng("작은 파일을 통과시켰다")
가짜zip = os.path.join(d, "b.zip")
open(가짜zip, "wb").write(b"NOTZIP" + b"0" * 200000)
res = drv.받은파일검사(가짜zip)
ok("압축이 아니면 거부") if not res[0] else ng("아무 파일이나 실행하려 했다")

print("\n6. 공식 도메인이 아니면 아예 받지 않는다")
res = drv.내려받기("https://example.com/evil.zip", "/tmp/x")
ok("다른 주소는 거부") if not res[0] and "허용되지 않은" in res[1] else ng("아무 데서나 받는다")

print(f"\n결과  통과 {P}건 · 실패 {F}건")
sys.exit(1 if F else 0)
