#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_setup.py — 처음 한 번만 준비하고, 그다음부터는 바로 실행한다.

이 파일은 사람이 직접 부르지 않는다. 다음 셋이 부른다.
    로봇손_따라하기.bat   웹캠으로 손을 인식해 로봇손을 움직인다  ← 본래 기능
    연결진단.bat          카메라와 로봇 포트가 잡히는지 본다
    웹캠만_보기.bat       로봇 없이 화면에만 그린다

★이름이 영문인 이유: 윈도우 cmd 는 bat 을 CP949 로 읽어, bat 안에 적힌
  한글 파일명이 깨져 파일을 못 찾는다. 그래서 bat 이 참조하는 이름은 영문으로 둔다.

★COM 번호를 사람이 몰라도 되게 만들었다 (2026-09-10 j2w 가 막힌 지점)
  더블클릭으로는 `--port COM3` 같은 인자를 줄 방법이 없다. 명령 프롬프트를
  열게 하는 것은 「원클릭」이 아니다. 그래서 **프로그램이 포트를 스스로 찾고,
  여럿이면 번호를 보여 주고 고르게** 한다.

★무슨 일이 있었는지 항상 실행기록.txt 에 남긴다
  화면은 창이 닫히면 사라진다. 막혔을 때 그 파일 하나만 있으면 원인을 알 수 있다.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv")
SRC = os.path.join(HERE, "src", "hand_tracking_control.py")
SDK = os.path.join(HERE, "brainco-hand-sdk")
PORTS_HELPER = os.path.join(HERE, "_ports.py")
CAMS_HELPER = os.path.join(HERE, "_cams.py")
SURVEY_HELPER = os.path.join(HERE, "_survey.py")
DRIVER_HELPER = os.path.join(HERE, "_driver.py")
SURVEY_TXT = os.path.join(HERE, "환경조사.txt")
LOGF = os.path.join(HERE, "실행기록.txt")
IS_WINDOWS = (os.name == "nt")

PKGS_BASE = ["opencv-python", "mediapipe"]
# ★colorlog 를 빼면 로봇 경로에서 「No module named 'colorlog'」로 막힌다.
#   제조사 SDK 예제(logger.py)가 쓰는데 bc-stark-sdk 가 끌어오지 않는다.
# pyserial 은 윈도우가 아는 COM 포트를 그대로 읽는다. 제조사 SDK 가
# 못 찾을 때 「장치는 있는데 SDK 가 못 알아본다」를 구분해 준다.
PKGS_ROBOT = ["bc-stark-sdk", "colorlog", "pyserial"]

PORT_MARK = "<<<PORTS>>>"
CAM_MARK = "<<<CAMS>>>"
_LAST_PORT_INFO = {}   # 마지막 포트 조회의 자세한 내용
SURVEY_MARK = "<<<SURVEY>>>"
DRIVER_MARK = "<<<DRIVER>>>"


# ─────────────────────────────────────────────────────────────────────────
#  화면과 기록
# ─────────────────────────────────────────────────────────────────────────
def say(msg=""):
    print(msg, flush=True)
    try:
        with open(LOGF, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except Exception:
        pass


def title(msg):
    say()
    say("=" * 66)
    say(f"  {msg}")
    say("=" * 66)


def hold(msg="  엔터를 누르면 창이 닫힙니다. "):
    """창이 그냥 닫히면 사람은 아무것도 못 본다. 어떤 길로 끝나든 여기서 멈춘다."""
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        pass


def die(msg, hint=""):
    say()
    say("=" * 66)
    say(f"  [멈춤] {msg}")
    if hint:
        say()
        for line in hint.splitlines():
            say(f"  {line}")
    say()
    say(f"  무슨 일이 있었는지 이 파일에 적어 두었습니다:")
    say(f"    {LOGF}")
    say("  이 파일을 보내 주시면 원인을 바로 알 수 있습니다.")
    say("=" * 66)
    say()
    hold()
    sys.exit(1)


def start_log(mode):
    try:
        with open(LOGF, "a", encoding="utf-8") as fh:
            fh.write("\n" + "#" * 70 + "\n")
            fh.write(f"# 실행 {time.strftime('%Y-%m-%d %H:%M:%S')}  모드 {mode}\n")
            fh.write(f"# 운영체제 {platform.platform()}\n")
            fh.write(f"# 파이썬   {sys.version.split()[0]} "
                     f"({'64비트' if sys.maxsize.bit_length() >= 63 else '32비트'})\n")
            fh.write(f"# 폴더     {HERE}\n")
            fh.write("#" * 70 + "\n")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
#  준비
# ─────────────────────────────────────────────────────────────────────────
def venv_python(venv_dir=VENV):
    if IS_WINDOWS:
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def check_this_python():
    is_64bit = sys.maxsize.bit_length() >= 63
    ver = sys.version_info[:2]
    if not is_64bit:
        die("32비트 파이썬입니다. 64비트가 필요합니다.",
            "python.org 에서 'Windows installer (64-bit)' 를 받아 다시 설치하십시오.")
    if not ((3, 9) <= ver < (3, 15)):
        die(f"파이썬 {ver[0]}.{ver[1]} 은 지원하지 않습니다 (3.9 ~ 3.14 필요).",
            "python.org 에서 3.12 를 받아 설치한 뒤 다시 실행하십시오.")


def make_venv():
    vpy = venv_python()
    if os.path.exists(vpy):
        return vpy
    title("처음 한 번만 — 프로그램 전용 자리를 만듭니다")
    say(f"  위치 : {VENV}")
    say("  이 폴더 안에만 넣으므로 컴퓨터의 다른 파이썬은 건드리지 않습니다.")
    say()
    r = subprocess.run([sys.executable, "-m", "venv", VENV])
    if r.returncode != 0 or not os.path.exists(vpy):
        die("전용 자리를 만들지 못했습니다.",
            "디스크 여유와 폴더 쓰기 권한을 확인하십시오.\n"
            "바탕화면이나 문서 폴더에 두고 다시 해 보십시오.\n"
            "(회사 PC 에서 Program Files 아래에 두면 막히는 일이 있습니다)")
    return vpy


def needed_packages(mode):
    return PKGS_BASE + (PKGS_ROBOT if mode in ("robot", "diag", "survey") else [])


def pip_install(vpy, pkgs, what):
    say(f"  {what} 을(를) 넣습니다 ...")
    r = subprocess.run([vpy, "-m", "pip", "install", "--upgrade"] + list(pkgs))
    if r.returncode != 0:
        die(f"{what} 설치에 실패했습니다.",
            "① 인터넷 연결 확인\n"
            "② 회사 방화벽이 pypi.org 를 막고 있을 수 있습니다\n"
            "③ 잠시 뒤 다시 실행해 보십시오")


def ensure_packages(vpy, mode):
    # ★표식 이름에 꾸러미 목록을 넣는다. 목록이 바뀌었는데 표식이 그대로면
    #   「이미 준비됨」으로 건너뛰어, 새로 필요해진 꾸러미가 영영 안 깔린다.
    import hashlib
    키 = hashlib.md5(",".join(sorted(needed_packages(mode))).encode()).hexdigest()[:8]
    stamp = os.path.join(VENV, f".준비완료_{mode}_{키}")
    if os.path.exists(stamp):
        return
    title("처음 한 번만 — 필요한 것을 내려받습니다")
    say("  약 300 MB 를 받습니다. 인터넷 상태에 따라 3~10분 걸립니다.")
    say("  창을 닫지 마십시오. 다음부터는 이 과정이 없습니다.")
    say()
    subprocess.run([vpy, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    pip_install(vpy, PKGS_BASE, "카메라·손추적 꾸러미")
    if mode in ("robot", "diag", "survey"):
        pip_install(vpy, PKGS_ROBOT, "로봇손 통신 꾸러미")
    with open(stamp, "w", encoding="utf-8") as fh:
        fh.write("ok\n")


# ─────────────────────────────────────────────────────────────────────────
#  포트 — 사람이 COM 번호를 몰라도 되게 한다
# ─────────────────────────────────────────────────────────────────────────
def run_and_log(cmd, env):
    """자식 프로그램을 돌리면서 그 출력을 화면과 기록에 **동시에** 남긴다.

    ★subprocess.run 으로 그냥 돌리면 자식 출력이 실행기록.txt 에 안 남는다.
      2026-09-10 에 그 때문에 「왜 실패했는지」가 통째로 빠졌고, 기록을
      받고도 원인을 알 수 없었다. 기록을 남기는 장치를 만들어 놓고 정작
      가장 중요한 부분을 빠뜨린 셈이다.
    """
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", bufsize=1)
    except Exception as e:
        say(f"  [실행 실패] {type(e).__name__}: {e}")
        return 1
    try:
        for line in proc.stdout:
            say(line.rstrip("\n"))
    except Exception as e:
        say(f"  [출력을 읽는 중 오류] {type(e).__name__}: {e}")
    proc.wait()
    return proc.returncode


def base_env():
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    if os.path.isdir(os.path.join(SDK, "python", "revo2")):
        env["STARK_SDK_DIR"] = SDK
    return env


def read_ports(vpy):
    """(성공여부, 포트이름목록, 오류설명) 을 돌려준다."""
    try:
        r = subprocess.run([vpy, PORTS_HELPER, SDK], env=base_env(),
                           capture_output=True, text=True, timeout=60)
    except Exception as e:
        return False, [], f"포트 조회를 실행하지 못했습니다: {type(e).__name__}: {e}"
    합 = (r.stdout or "") + "\n" + (r.stderr or "")
    줄 = [l for l in 합.splitlines() if l.startswith(PORT_MARK)]
    if not 줄:
        return False, [], ("포트 조회가 답을 주지 않았습니다.\n"
                           + (합.strip()[-500:] if 합.strip() else "(출력 없음)"))
    try:
        d = json.loads(줄[-1][len(PORT_MARK):])
    except Exception as e:
        return False, [], f"포트 조회 결과를 읽지 못했습니다: {e}"
    if not d.get("ok"):
        return False, [], f"[{d.get('step')}] {d.get('error')}"
    global _LAST_PORT_INFO
    _LAST_PORT_INFO = d
    return True, list(d.get("ports") or []), ""


def run_survey(vpy):
    """이 컴퓨터를 조사한다. (성공여부, 결과딕셔너리, 오류설명)"""
    try:
        r = subprocess.run([vpy, SURVEY_HELPER, SDK], env=base_env(),
                           capture_output=True, text=True, timeout=240)
    except Exception as e:
        return False, {}, f"조사를 실행하지 못했습니다: {type(e).__name__}: {e}"
    합 = (r.stdout or "") + "\n" + (r.stderr or "")
    줄 = [l for l in 합.splitlines() if l.startswith(SURVEY_MARK)]
    if not 줄:
        return False, {}, ("조사가 답을 주지 않았습니다.\n"
                           + (합.strip()[-600:] if 합.strip() else "(출력 없음)"))
    try:
        return True, json.loads(줄[-1][len(SURVEY_MARK):]), ""
    except Exception as e:
        return False, {}, f"조사 결과를 읽지 못했습니다: {e}"


def 드라이버설치(vpy, 후보):
    """드라이버를 설치한다. 무엇을 하는지 알리고 **동의를 받은 뒤에만** 진행한다.

    ★관리자 권한이 필요한 유일한 단계다.
      파이썬은 계정 안에만 넣어 권한이 필요 없었지만, 드라이버는 시스템에
      등록해야 하므로 예외다. UAC 창은 **사람이 승인**한다 — 대신 눌러 주지 않는다.
    """
    c = 후보[0]
    say()
    say("=" * 66)
    say("  로봇손 드라이버를 설치하시겠습니까?")
    say("=" * 66)
    say(f"    찾은 장치 : {c['이름']}   VID:{c['vid']} PID:{c['pid']}")
    say(f"    칩       : {c['칩']}")
    say(f"    설치할 것 : {c['드라이버']} 드라이버")
    say()
    say("  이렇게 진행합니다.")
    say("    ① 먼저 윈도우 업데이트로 시도합니다 (파일을 받지 않습니다)")
    say("    ② 안 되면 제조사 공식 사이트에서 설치 파일을 받아 실행합니다")
    say(f"       ({c['링크']})")
    say()
    say("  ★관리자 권한 창이 뜹니다. 「예」를 눌러 주셔야 설치됩니다.")
    say("    (드라이버는 시스템에 등록해야 하므로 권한이 필요합니다)")
    say()
    try:
        답 = input("  설치할까요? (y = 예 / 그 밖 = 아니오): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        답 = ""
    if 답 not in ("y", "yes", "ㅛ"):
        say("  설치하지 않았습니다. 직접 설치하시려면 위 주소에서 받으십시오.")
        return False

    say()
    say("  설치를 시작합니다. 창이 뜨면 「예」를 눌러 주십시오 ...")
    try:
        r = subprocess.run([vpy, DRIVER_HELPER, c["드라이버"]], env=base_env(),
                           capture_output=True, text=True, timeout=1200,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        say(f"  설치를 실행하지 못했습니다: {type(e).__name__}: {e}")
        return False
    합 = (r.stdout or "") + "\n" + (r.stderr or "")
    줄 = [l for l in 합.splitlines() if l.startswith(DRIVER_MARK)]
    if not 줄:
        say("  설치 도우미가 답을 주지 않았습니다.")
        say(합.strip()[-400:])
        return False
    try:
        d = json.loads(줄[-1][len(DRIVER_MARK):])
    except Exception as e:
        say(f"  설치 결과를 읽지 못했습니다: {e}")
        return False
    if d.get("ok"):
        say(f"  ✔ {d.get('message','설치를 마쳤습니다.')}")
        say()
        say("  ★USB 케이블을 뽑았다가 다시 꽂아 주십시오.")
        say("    그래야 윈도우가 새 드라이버로 장치를 다시 잡습니다.")
        try:
            input("  다시 꽂으셨으면 엔터를 누르십시오. ")
        except (EOFError, KeyboardInterrupt):
            pass
        return True
    say(f"  설치하지 못했습니다: {d.get('error','')}")
    if d.get("page"):
        say(f"  받는 곳을 브라우저로 열었습니다: {d['page']}")
    say()
    say("  " + "=" * 62)
    say("  ★손으로 설치하는 방법 (5분)")
    say("  " + "=" * 62)
    say("    ※「드라이버를 자동으로 검색」은 이 PC 에서 실패합니다.")
    say("      윈도우 업데이트에서 드라이버를 못 가져오는 상태이기 때문입니다.")
    say("      그래서 **파일을 받아 직접 지정**해야 합니다.")
    say()
    say("    ① 다음 주소에서 CDM 드라이버를 받습니다 (브라우저를 열어 드렸습니다)")
    say("         https://ftdichip.com/drivers/vcp-drivers/")
    say("       「Windows (Desktop)」 줄에서 setup executable 을 받으십시오.")
    say("    ② 받은 zip 을 **압축 풀기** 합니다 (예: 바탕화면에 풀기)")
    say("    ③ 푼 폴더 안의  CDM...exe  를 두 번 눌러 설치합니다")
    say("       — 이것만으로 되는 경우가 많습니다.")
    say()
    say("    ④ 그래도 안 되면 장치 관리자에서 직접 지정합니다")
    say("         Win + X → 장치 관리자")
    say("         노란 느낌표의  FT231X USB UART  를 오른쪽 클릭")
    say("         → 드라이버 업데이트")
    say("         → ★「내 컴퓨터에서 드라이버 찾아보기」   ← 자동 검색이 아닙니다")
    say("         → ②에서 푼 폴더를 고르고 「하위 폴더 포함」 체크")
    say("    ⑤ USB 를 뽑았다 다시 꽂고, 이 프로그램을 다시 실행하십시오")
    say()
    say("    ★로봇손 제조사(BrainCo) 공식 자료실 — 드라이버·SDK·설명서")
    say("         https://www.brainco-hz.com/docs/revolimb-hand/en/revo2/download.html")
    say("       위 ①~④ 로 해결되지 않으면 여기서 최신 자료를 받으십시오.")
    say()
    say("    · 「포트(COM & LPT)」에 USB Serial Port (COMx) 가 생기면 성공입니다")
    say("  " + "=" * 62)
    return False


def 조사찍기(d, 자세히=True):
    """조사 결과를 사람이 읽을 수 있게 보여 준다."""
    say()
    say("─" * 66)
    say("  이 컴퓨터")
    say("─" * 66)
    comp = d.get("computer") or {}
    cpu = d.get("cpu") or {}
    osd = d.get("os_detail") or {}
    if comp or osd:
        say(f"    제조사·모델 : {comp.get('Manufacturer','?')} {comp.get('Model','')}")
        ram = comp.get("TotalPhysicalMemory")
        if ram:
            try:
                say(f"    메모리      : {int(ram)/1024**3:.1f} GB")
            except Exception:
                pass
        say(f"    프로세서    : {cpu.get('Name','?')}")
        say(f"    운영체제    : {osd.get('Caption','?')} {osd.get('OSArchitecture','')}")
    else:
        say(f"    운영체제    : {d.get('os','?')}")
    for g in (d.get("gpu") or []):
        say(f"    그래픽      : {g.get('Name','?')}  (드라이버 {g.get('DriverVersion','?')})")
    say(f"    파이썬      : {d.get('python','?')} ({d.get('python_bits','?')}비트)")

    say()
    say("─" * 66)
    say("  카메라")
    say("─" * 66)
    if d.get("camera_error"):
        say(f"    조회 실패: {d['camera_error']}")
    elif d.get("cameras"):
        for c in d["cameras"]:
            say(f"    {c['index']}번  {c['w']}x{c['h']}  ({c['backend']})")
    else:
        say("    없음")

    say()
    say("─" * 66)
    say("  로봇손이 붙을 자리")
    say("─" * 66)
    칩 = d.get("serial_chips") or []
    if 칩:
        say("    ★USB 직렬 변환 칩 (로봇손이 여기에 붙습니다)")
        for c in 칩:
            표 = "정상" if c.get("상태") == "OK" else f"★{c.get('상태')}"
            say(f"        [{표}] {c['이름']}   VID:{c['vid']} PID:{c['pid']}")
            say(f"              {c['칩']}")
    else:
        say("    ★USB 직렬 변환 칩 : 없음 (로봇손이 USB 에 안 보입니다)")
    say(f"    제조사 SDK 가 아는 포트 : {d.get('sdk_ports') or '없음'}"
        + (f"   ({d['sdk_error']})" if d.get("sdk_error") else ""))
    ser = d.get("serial_ports") or []
    if d.get("serial_error"):
        say(f"    직렬 포트 조회 실패     : {d['serial_error']}")
    else:
        usb_ser = [p for p in ser if p.get("vid") or "USB" in (p.get("hwid","")).upper()]
        say(f"    USB 직렬 포트           : "
            + (", ".join(p["device"] for p in usb_ser) if usb_ser else "없음")
            + (f"   (그 밖의 포트 {len(ser)-len(usb_ser)}개는 로봇이 아닙니다)"
               if len(ser) > len(usb_ser) else ""))
        for p_ in usb_ser:
            say(f"        {p_['device']}  {p_.get('desc','')}  "
                f"VID:{p_.get('vid','')} PID:{p_.get('pid','')}")
    com = d.get("com_devices") or []
    if com:
        say("    장치 관리자의 포트 항목 :")
        for it in com:
            say(f"        [{it.get('Status')}] {it.get('FriendlyName')}")
    if 자세히:
        usb = d.get("usb_devices") or []
        say(f"    USB 버스의 장치         : {len(usb)}개")
        문제 = d.get("problem_devices") or []
        # ★HID·키보드·저장장치까지 다 찍으면 정작 중요한 직렬 장치가 묻힌다.
        #   2026-09-10 에 실제로 FTDI 오류가 목록에서 잘려 안 보였다.
        관련 = [it for it in 문제
                if any(k in ((it.get("FriendlyName") or "") + (it.get("Class") or "")).upper()
                       for k in ("SERIAL", "UART", "COM", "PORT", "FTDI",
                                 "CH34", "CP21", "PL23"))]
        if 관련:
            say("    ★상태가 정상이 아닌 직렬 장치:")
            for it in 관련[:10]:
                say(f"        [{it.get('Status')}] {it.get('Class')} "
                    f"{it.get('FriendlyName')}")
        elif 문제:
            say(f"    (상태가 정상이 아닌 장치가 {len(문제)}개 있으나 "
                f"직렬 장치는 아닙니다)")


def 판정찍기(판정):
    say()
    say("=" * 66)
    상태 = 판정.get("상태")
    say(f"  판정 : {상태}")
    say("=" * 66)
    say(f"  {판정.get('말','')}")
    if 상태 == "드라이버필요":
        say()
        for c in 판정.get("후보", []):
            say(f"    · {c['이름']}   VID:{c['vid']} PID:{c['pid']}")
            say(f"      칩       : {c['칩']}")
            say(f"      필요한 것: {c['드라이버']} 드라이버")
            say(f"      받는 곳  : {c['링크']}")
        say()
        say("  ※ 이 상태는 「드라이버 파일이 없다」는 뜻입니다(오류 28).")
        say("    장치 관리자의 「자동으로 검색」은 이 PC 에서 실패합니다 —")
        act = "받아서 직접 지정"
        say(f"    윈도우 업데이트를 못 쓰는 상태라, 파일을 {act}해야 합니다.")
        say("    이 프로그램이 대신 해 드립니다. 아래 물음에 y 로 답해 주십시오.")
    elif 상태 == "장치이상":
        say()
        for c in 판정.get("의심", [])[:8]:
            say(f"    · [{c.get('Status')}] {c.get('FriendlyName')}")
        say()
        say("  장치 관리자(Win+X → 장치 관리자)에서 노란 느낌표를 확인하십시오.")
    elif 상태 == "장치없음":
        say()
        say("    ① USB 케이블을 다른 포트에 꽂아 보십시오 (앞면 대신 뒷면)")
        say("    ② ★24V DC 어댑터를 꽂으십시오")
        say("    ③ 케이블이 「충전 전용」이 아닌 데이터 케이블인지 확인하십시오")
    say("=" * 66)


def read_cams(vpy):
    """(성공여부, 카메라목록, 오류설명)"""
    try:
        r = subprocess.run([vpy, CAMS_HELPER], env=base_env(),
                           capture_output=True, text=True, timeout=120)
    except Exception as e:
        return False, [], f"카메라 조회를 실행하지 못했습니다: {type(e).__name__}: {e}"
    합 = (r.stdout or "") + "\n" + (r.stderr or "")
    줄 = [l for l in 합.splitlines() if l.startswith(CAM_MARK)]
    if not 줄:
        return False, [], ("카메라 조회가 답을 주지 않았습니다.\n"
                           + (합.strip()[-500:] if 합.strip() else "(출력 없음)"))
    try:
        d = json.loads(줄[-1][len(CAM_MARK):])
    except Exception as e:
        return False, [], f"카메라 조회 결과를 읽지 못했습니다: {e}"
    if not d.get("ok"):
        return False, [], str(d.get("error"))
    return True, list(d.get("cams") or []), ""


def choose_camera(vpy, 지정=None):
    """쓸 카메라 번호를 정한다. 못 정하면 멈춘다."""
    if 지정 is not None:
        say(f"  카메라를 직접 지정하셨습니다: {지정}")
        return 지정
    say("  쓸 수 있는 카메라를 찾습니다 ...")
    ok, cams, err = read_cams(vpy)
    if not ok:
        say("  [알림] 카메라 목록을 읽지 못했습니다.")
        for line in err.splitlines():
            say(f"         {line}")
        say("  그래도 0번으로 시도해 봅니다.")
        return "0"
    if not cams:
        die("쓸 수 있는 카메라를 찾지 못했습니다.",
            "확인 순서\n"
            "  ① 웹캠이 꽂혀 있는지 보십시오 (노트북 내장 카메라도 됩니다)\n"
            "  ② ★줌·팀즈·카메라 앱 등 카메라를 쓰는 프로그램을 모두 닫으십시오\n"
            "     윈도우는 한 번에 한 프로그램만 카메라를 쓸 수 있습니다.\n"
            "  ③ 설정 → 개인 정보 → 카메라 에서 두 가지를 모두 켜십시오\n"
            "     · 앱이 카메라에 액세스하도록 허용\n"
            "     · ★데스크톱 앱이 카메라에 액세스하도록 허용  ← 자주 꺼져 있습니다\n"
            "  ④ 카메라 덮개(프라이버시 셔터)가 닫혀 있지 않은지 보십시오"
            if IS_WINDOWS else
            "  ① 웹캠 연결  ② ls /dev/video*  ③ 다른 프로그램이 쓰고 있는지")
    if len(cams) == 1:
        c = cams[0]
        say(f"  ✔ 카메라를 찾았습니다: {c['index']}번 "
            f"({c['w']}x{c['h']}, {c['backend']})")
        return str(c["index"])
    say()
    say(f"  카메라가 {len(cams)}개 보입니다. 쓸 것을 고르십시오.")
    for i, c in enumerate(cams, 1):
        say(f"    {i}) {c['index']}번  {c['w']}x{c['h']}  ({c['backend']})")
    say()
    for _ in range(3):
        try:
            sel = input(f"  번호 [1-{len(cams)}] (그냥 엔터 = 1번): ").strip()
        except (EOFError, KeyboardInterrupt):
            return str(cams[0]["index"])
        if sel == "":
            return str(cams[0]["index"])
        if sel.isdigit() and 1 <= int(sel) <= len(cams):
            골라 = cams[int(sel) - 1]
            say(f"  → {골라['index']}번을 씁니다.")
            return str(골라["index"])
        say(f"  1 ~ {len(cams)} 중에서 고르십시오.")
    return str(cams[0]["index"])


def choose_port(vpy, 지정=None):
    """쓸 포트를 정한다. 못 정하면 None 을 돌려준다(그러면 실행하지 않는다)."""
    if 지정:
        say(f"  포트를 직접 지정하셨습니다: {지정}")
        return 지정

    say("  로봇손이 붙은 포트를 찾습니다 ...")
    ok, ports, err = read_ports(vpy)
    if not ok:
        say()
        say("  [알림] 포트 목록을 읽지 못했습니다.")
        for line in err.splitlines():
            say(f"         {line}")
        say()
        say("  그래도 진행해 봅니다 — SDK 가 스스로 찾을 수도 있습니다.")
        return None

    if not ports:
        d = _LAST_PORT_INFO
        문제 = d.get("win_problem") or []
        보임 = d.get("win_com") or []
        if 보임 or 문제:
            say()
            say("  참고 — 윈도우가 아는 장치는 이렇습니다:")
            for it in 보임:
                say(f"    [{it.get('Status')}] {it.get('FriendlyName')}")
            for it in 문제:
                say(f"    [{it.get('Status')}] {it.get('Class')} {it.get('FriendlyName')}")
        die("로봇손을 찾지 못했습니다. 연결된 직렬 포트가 하나도 없습니다.",
            "확인 순서\n"
            "  ① ★24V DC 어댑터를 꽂으십시오\n"
            "     USB 는 통신 전용이라 전원 없이는 아무 응답이 없습니다.\n"
            "     이것이 가장 흔한 원인입니다.\n"
            "  ② USB 케이블을 꽂으십시오 (다른 포트에도 꽂아 보십시오)\n"
            "  ③ 장치 관리자 → 포트(COM & LPT) 에 항목이 보이는지 확인하십시오\n"
            "     안 보이면 USB 직렬 드라이버(CP210x 또는 CH340)를 설치하십시오\n"
            "  ④ 다른 프로그램이 그 포트를 잡고 있지 않은지 확인하십시오"
            if IS_WINDOWS else
            "확인 순서\n"
            "  ① ★24V DC 어댑터  ② USB 케이블\n"
            "  ③ ls /dev/ttyUSB*  ④ dialout 그룹 권한")

    if len(ports) == 1:
        say(f"  ✔ 포트를 찾았습니다: {ports[0]}")
        return ports[0]

    # 여러 개 — 사람이 고른다 (COM 번호를 미리 알 필요가 없다)
    say()
    say(f"  포트가 {len(ports)}개 보입니다. 로봇손이 붙은 것을 고르십시오.")
    say("  (블루투스나 가상 포트가 함께 보일 수 있습니다)")
    say()
    for i, name in enumerate(ports, 1):
        say(f"    {i}) {name}")
    say()
    for _ in range(3):
        try:
            sel = input(f"  번호 [1-{len(ports)}] (그냥 엔터 = 1번): ").strip()
        except (EOFError, KeyboardInterrupt):
            return ports[0]
        if sel == "":
            return ports[0]
        if sel.isdigit() and 1 <= int(sel) <= len(ports):
            골라 = ports[int(sel) - 1]
            say(f"  → {골라} 를 씁니다.")
            return 골라
        say(f"  1 ~ {len(ports)} 중에서 고르십시오.")
    say("  세 번 잘못 넣어 1번을 씁니다.")
    return ports[0]


# ─────────────────────────────────────────────────────────────────────────
#  실행
# ─────────────────────────────────────────────────────────────────────────
def run_diag(vpy):
    """빠른 확인. 조사기를 써서 판정까지 보여 준다."""
    ok, d, err = run_survey(vpy)
    if ok:
        조사찍기(d, 자세히=True)
        판정찍기(d.get("판정") or {})
        try:
            with open(SURVEY_TXT, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(d, ensure_ascii=False, indent=2))
            say()
            say(f"  자세한 내용: {SURVEY_TXT}")
        except Exception:
            pass
        return 0
    say("  조사에 실패해 예전 방식으로 확인합니다:")
    for line in err.splitlines():
        say(f"    {line}")
    env = base_env()
    title("① 카메라를 찾습니다")
    ok, cams, err = read_cams(vpy)
    if not ok:
        say("  카메라 목록을 읽지 못했습니다:")
        for line in err.splitlines():
            say(f"    {line}")
    elif not cams:
        say("  없음. 쓸 수 있는 카메라가 하나도 없습니다.")
        if IS_WINDOWS:
            say("  → ★줌·팀즈·카메라 앱을 모두 닫으십시오 (한 번에 하나만 쓸 수 있습니다)")
            say("  → 설정 → 개인 정보 → 카메라 →")
            say("     「데스크톱 앱이 카메라에 액세스하도록 허용」이 켜져 있는지 보십시오")
            say("  → 카메라 덮개가 닫혀 있지 않은지 보십시오")
    else:
        say(f"  {len(cams)}개를 찾았습니다:")
        for c in cams:
            say(f"    {c['index']}번  {c['w']}x{c['h']}  ({c['backend']})")
    title("② 로봇손이 붙을 포트를 찾습니다")
    ok, ports, err = read_ports(vpy)
    if not ok:
        say("  포트 목록을 읽지 못했습니다:")
        for line in err.splitlines():
            say(f"    {line}")
    else:
        d = _LAST_PORT_INFO
        say("  ─ 제조사 SDK 가 아는 포트")
        if d.get("sdk_error"):
            say(f"      (조회 실패: {d['sdk_error']})")
        elif d.get("sdk_ports"):
            for n in d["sdk_ports"]:
                say(f"      {n}")
        else:
            say("      없음")

        say("  ─ USB 로 붙은 직렬 포트 (pyserial)")
        if d.get("serial_error"):
            say(f"      (조회 실패: {d['serial_error']})")
        elif d.get("usb_serial"):
            for it in d["serial_ports"]:
                if it.get("device") in d["usb_serial"]:
                    say(f"      {it.get('device')}   {it.get('desc')}")
                    if it.get("hwid"):
                        say(f"        {it['hwid']}")
        else:
            전체 = len(d.get("serial_ports") or [])
            say(f"      없음   (USB 가 아닌 포트는 {전체}개 보이지만 로봇이 아닙니다)")

        if IS_WINDOWS:
            say("  ─ 장치 관리자의 포트(COM & LPT) 항목")
            if d.get("win_com"):
                for it in d["win_com"]:
                    say(f"      [{it.get('Status')}] {it.get('FriendlyName')}")
            else:
                say("      없음")
            문제 = d.get("win_problem") or []
            if 문제:
                say("  ─ ★상태가 정상이 아닌 장치 (드라이버가 없을 수 있습니다)")
                for it in 문제:
                    say(f"      [{it.get('Status')}] {it.get('Class')} "
                        f"{it.get('FriendlyName')}")

        say()
        if ports:
            say(f"  ▶ 쓸 수 있는 포트: {', '.join(ports)}")
    say()
    say("=" * 66)
    say("  카메라와 포트가 모두 나와야 로봇이 손을 따라 움직입니다.")
    say(f"  이 내용은 {os.path.basename(LOGF)} 에도 적어 두었습니다.")
    say("=" * 66)
    return 0


def run_survey_mode(vpy):
    title("이 컴퓨터를 조사합니다 (아무것도 바꾸지 않습니다)")
    say("  하드웨어·USB 장치·포트·드라이버 상태를 살펴봅니다. 30초쯤 걸립니다.")
    ok, d, err = run_survey(vpy)
    if not ok:
        say("  조사에 실패했습니다:")
        for line in err.splitlines():
            say(f"    {line}")
        return 1
    조사찍기(d)
    판정찍기(d.get("판정") or {})
    try:
        with open(SURVEY_TXT, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False, indent=2))
        say()
        say(f"  자세한 내용을 파일로 저장했습니다: {SURVEY_TXT}")
        say("  막히면 이 파일을 보내 주십시오.")
    except Exception as e:
        say(f"  (조사 결과 저장 실패: {e})")
    return 0


def run_body(vpy, mode, passthrough):
    if mode == "survey":
        return run_survey_mode(vpy)
    if mode == "diag":
        return run_diag(vpy)

    env = base_env()

    카메라지정 = None
    if "--source" in passthrough:
        i = passthrough.index("--source")
        if i + 1 < len(passthrough):
            카메라지정 = passthrough[i + 1]
    포트지정 = None
    if "--port" in passthrough:
        i = passthrough.index("--port")
        if i + 1 < len(passthrough):
            포트지정 = passthrough[i + 1]

    title("웹캠으로 손을 따라 로봇손을 움직입니다" if mode == "robot"
          else "웹캠 손추적만 봅니다 (로봇은 움직이지 않습니다)")

    # ★이 컴퓨터를 먼저 조사해서 **여기에 맞게** 정한다 (j2w 요청 2026-09-10)
    #   「포트가 없다」로 끝내지 않고, USB 버스까지 내려가 원인을 가려낸다.
    #     · 쓸 포트가 있다      → 그것으로 바로 실행
    #     · USB 로만 보인다      → 어느 드라이버가 필요한지 알려 준다
    #     · 아무 데도 없다       → 케이블·전원 문제
    조사 = {}
    if mode == "robot" and (포트지정 is None or 카메라지정 is None):
        say("  이 컴퓨터를 살펴봅니다 ...")
        ok, 조사, err = run_survey(vpy)
        if not ok:
            say("  (조사에 실패했습니다. 예전 방식으로 찾아봅니다)")
            for line in err.splitlines():
                say(f"    {line}")
            조사 = {}

    # 카메라 정하기
    if 카메라지정 is not None:
        src = 카메라지정
    elif 조사.get("cameras"):
        c = 조사["cameras"][0]
        src = str(c["index"])
        say(f"  ✔ 카메라 {c['index']}번 ({c['w']}x{c['h']}, {c['backend']})")
    else:
        src = choose_camera(vpy)
    cmd = [vpy, SRC] + ([] if 카메라지정 is not None else ["--source", src])

    if mode == "robot":
        # 포트 정하기 — 조사 결과의 판정을 따른다
        고른 = None
        if 포트지정 is not None:
            say(f"  포트를 직접 지정하셨습니다: {포트지정}")
        elif 조사:
            판정 = 조사.get("판정") or {}
            상태 = 판정.get("상태")
            if 상태 == "준비됨":
                포트들 = 판정.get("포트") or []
                if len(포트들) == 1:
                    고른 = 포트들[0]
                    say(f"  ✔ 로봇손 포트 {고른}")
                else:
                    say()
                    say(f"  포트가 {len(포트들)}개 보입니다. 로봇손이 붙은 것을 고르십시오.")
                    for i, n in enumerate(포트들, 1):
                        say(f"    {i}) {n}")
                    try:
                        sel = input(f"  번호 [1-{len(포트들)}] (엔터 = 1번): ").strip()
                    except (EOFError, KeyboardInterrupt):
                        sel = ""
                    고른 = 포트들[int(sel) - 1] if (sel.isdigit()
                            and 1 <= int(sel) <= len(포트들)) else 포트들[0]
                    say(f"  → {고른} 를 씁니다.")
            elif 상태 == "드라이버필요" and 판정.get("후보"):
                # 드라이버만 깔면 되는 상황이다. 설치를 제안한다.
                조사찍기(조사, 자세히=False)
                판정찍기(판정)
                if 드라이버설치(vpy, 판정["후보"]):
                    say()
                    say("  다시 살펴봅니다 ...")
                    ok2, 조사2, _ = run_survey(vpy)
                    판정2 = (조사2.get("판정") or {}) if ok2 else {}
                    포트들 = 판정2.get("포트") or []
                    if 판정2.get("상태") == "준비됨" and 포트들:
                        고른 = 포트들[0]
                        say(f"  ✔ 로봇손 포트 {고른}  — 이제 시작합니다")
                    else:
                        say()
                        say("  아직 포트가 보이지 않습니다.")
                        if ok2:
                            판정찍기(판정2)
                        say("  USB 를 다시 꽂고 이 프로그램을 한 번 더 실행해 주십시오.")
                        say()
                        hold()
                        return 1
                else:
                    say()
                    hold()
                    return 1
            else:
                # 쓸 포트가 없다 — 왜 없는지 알려 주고 멈춘다
                조사찍기(조사, 자세히=True)
                판정찍기(판정)
                try:
                    with open(SURVEY_TXT, "w", encoding="utf-8") as fh:
                        fh.write(json.dumps(조사, ensure_ascii=False, indent=2))
                    say()
                    say(f"  조사 결과를 저장했습니다: {SURVEY_TXT}")
                    say("  이 파일과 실행기록.txt 를 보내 주시면 원인을 정확히 알 수 있습니다.")
                except Exception:
                    pass
                say()
                hold()
                return 1
        else:
            고른 = choose_port(vpy, None)

        cmd += ["--backend", "sdk", "--sdk-dir", SDK]
        if 고른 and 포트지정 is None:
            cmd += ["--port", 고른]
        say()
        say("  ★로봇손에 24V DC 어댑터가 꽂혀 있어야 합니다.")
        say("  창이 뜨면 카메라 앞에서 손을 펴고 쥐어 보십시오.")
        say("  로봇손이 그대로 따라 움직입니다.")
        say("  화면은 전체 화면으로 뜹니다. 창으로 보려면 f 키를 누르십시오.")
        say("  끝내려면 창을 클릭하고 q 키를 누르거나 창을 닫으십시오.")
    else:
        cmd += ["--backend", "none"]
        say("  창이 뜨면 카메라 앞에서 손을 펴고 쥐어 보십시오.")
        say("  화면은 전체 화면으로 뜹니다. 창으로 보려면 f 키를 누르십시오.")
        say("  끝내려면 창을 클릭하고 q 키를 누르거나 창을 닫으십시오.")

    cmd += list(passthrough)
    say()
    say(f"  (실행: {' '.join(os.path.basename(c) if c == vpy or c == SRC else c for c in cmd)})")
    say()

    rc = run_and_log(cmd, env)
    if rc != 0:
        say()
        say("  " + "=" * 62)
        say("  뜻대로 되지 않았습니다. 위 메시지를 먼저 보십시오.")
        say("  무엇이 빠졌는지 한 번에 보려면:   연결진단.bat")
        if mode == "robot":
            say()
            say("  로봇이 반응하지 않을 때")
            say("    ① ★24V DC 어댑터  ② USB 케이블  ③ 장치 관리자에서 COM 확인")
        say(f"  기록: {LOGF}")
        say("  이 파일을 보내 주시면 원인을 바로 알 수 있습니다.")
        say("  " + "=" * 62)
    return rc


def main():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--mode", default="robot", choices=["robot", "webcam", "diag", "survey"])
    args, rest = p.parse_known_args()

    start_log(args.mode)
    if not os.path.exists(SRC):
        die("본체 파일을 찾지 못했습니다: src/hand_tracking_control.py",
            "압축을 풀 때 폴더 전체를 함께 풀어야 합니다.")

    check_this_python()
    say(f"  파이썬 {sys.version.split()[0]}  "
        f"({'64비트' if sys.maxsize.bit_length() >= 63 else '32비트'})")
    vpy = make_venv()
    ensure_packages(vpy, args.mode)
    rc = run_body(vpy, args.mode, rest)

    say()
    hold()
    return rc


if __name__ == "__main__":
    sys.exit(main())
