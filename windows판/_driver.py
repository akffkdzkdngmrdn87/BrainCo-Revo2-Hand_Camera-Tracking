#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_driver.py — USB 직렬 변환 칩의 드라이버를 설치한다 (윈도우 전용).

★왜 필요한가 (2026-09-10)
  로봇손은 FTDI FT231X 칩으로 PC 와 통신한다. 그 드라이버가 없으면 장치는
  USB 에 보이는데 **COM 포트가 만들어지지 않아** 프로그램이 로봇을 못 찾는다.
  PC 를 바꿀 때마다 사람이 드라이버를 찾아 깔게 하는 것은 번거롭다.

★어디까지 자동으로 하는가 — 그리고 왜 거기까지인가
  드라이버 설치는 **관리자 권한**이 필요하다. 파이썬 설치와 달리 계정 안에만
  넣을 수 없다. 그래서 이 프로그램은
      · 무엇을 왜 설치하는지 먼저 알리고 동의를 받는다
      · 관리자 권한 창(UAC)을 띄운다 — **승인은 사람이 한다**
      · 공식 도메인(ftdichip.com)에서만 받고, 받은 파일을 검사한 뒤 실행한다
  UAC 를 대신 눌러 주지 않는다. 그렇게 만들면 안 된다.

순서
  ① 윈도우 업데이트로 먼저 시도한다 (파일을 내려받지 않아 가장 안전하다)
  ② 안 되면 제조사 공식 설치 파일을 받아 실행한다
  ③ 그래도 안 되면 받는 곳을 브라우저로 열어 준다
"""
import json
import os
import subprocess
import sys
import tempfile

MARK = "<<<DRIVER>>>"
IS_WINDOWS = (os.name == "nt")

# 공식 배포처. 여러 판이 있으므로 앞에서부터 시도한다.
FTDI_URLS = [
    "https://ftdichip.com/wp-content/uploads/2021/08/CDM212364_Setup.zip",
    "https://ftdichip.com/wp-content/uploads/2023/09/CDM-v2.12.36.4-WHQL-Certified.zip",
]
FTDI_PAGE = "https://ftdichip.com/drivers/vcp-drivers/"

# ★로봇손 제조사(BrainCo) 공식 자료실 — 드라이버·SDK·문서를 여기서 받는다.
#   이 프로그램은 **먼저 자동 설치를 시도하고**, 그것이 안 될 때
#   사람이 **직접 받아 설치**할 수 있도록 아래 주소를 안내한다(2026-09-22 j2w 지시).
#   드라이버 설치는 관리자 권한이 필요하고 배포 주소가 바뀌기도 하므로,
#   끝까지 대신 해 주려 들지 않고 받는 곳을 알려 주는 편이 안전하다.
BRAINCO_PAGE = "https://www.brainco-hz.com/docs/revolimb-hand/en/revo2/download.html"
BRAINCO_SDK = "https://github.com/BrainCoTech/brainco-hand-sdk"

CHIP_PAGES = {
    "FTDI VCP": FTDI_PAGE,
    "CP210x": "https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers",
    "CH340": "https://www.wch-ic.com/downloads/CH341SER_EXE.html",
    "PL2303": "https://www.prolific.com.tw/US/ShowProduct.aspx?p_id=225&pcid=41",
}


def out(**kw):
    print(MARK + json.dumps(kw, ensure_ascii=False))


def ps_runas(exe, args, wait=True):
    """관리자 권한으로 실행한다. UAC 창이 뜨고 승인은 사람이 한다."""
    cmd = (f"$p = Start-Process -FilePath '{exe}' "
           f"-ArgumentList '{args}' -Verb RunAs -PassThru"
           + (" -Wait" if wait else "")
           + "; if ($p) { exit $p.ExitCode } else { exit 1 }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", cmd],
                           capture_output=True, text=True, timeout=900,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def 직렬장치상태(vid="0403"):
    """그 칩의 장치가 지금 어떤 상태인지 본다. (상태 목록)"""
    items = ps_json(
        "$ErrorActionPreference='SilentlyContinue';"
        "Get-PnpDevice -PresentOnly | "
        f"Where-Object {{ $_.InstanceId -like '*VID_{vid}*' }} | "
        "Select-Object Status,FriendlyName,InstanceId | ConvertTo-Json -Compress")
    return [it.get("Status") for it in items]


def com포트수():
    """지금 존재하는 COM 포트 이름들."""
    items = ps_json(
        "$ErrorActionPreference='SilentlyContinue';"
        "Get-PnpDevice -Class Ports -PresentOnly | "
        "Select-Object FriendlyName | ConvertTo-Json -Compress")
    return [it.get("FriendlyName", "") for it in items]


def 드라이버붙었나(vid="0403"):
    """★종료코드가 아니라 **실제 상태**로 판정한다.

    pnputil /scan-devices 는 장치를 다시 훑기만 하고, 드라이버가 시스템에
    없으면 아무 일도 하지 않는다. **그런데도 종료코드는 0 이다.**
    2026-09-10 에 그것을 성공으로 읽어 실제 설치 단계로 넘어가지 않았다.
    (같은 실수를 그날 자체 WiFi 에서도 했다 — 종료코드를 믿지 마라)
    """
    상태 = 직렬장치상태(vid)
    if 상태 and all(s == "OK" for s in 상태):
        return True
    # 상태를 못 읽었더라도 USB 직렬 COM 포트가 생겼으면 된 것이다
    return any(("USB" in n.upper() or "SERIAL" in n.upper()) for n in com포트수())


def 윈도우업데이트로시도(vid="0403"):
    """장치를 다시 훑어 윈도우가 드라이버를 가져오게 한다. 파일을 받지 않는다."""
    rc, msg = ps_runas("pnputil.exe", "/scan-devices")
    # 종료코드가 아니라 실제로 붙었는지로 판정한다
    import time as _t
    _t.sleep(3)
    return 드라이버붙었나(vid), f"(pnputil 종료코드 {rc}) " + msg[-200:]


def 내려받기(url, dest):
    """공식 도메인에서만 받는다."""
    if not url.startswith("https://ftdichip.com/"):
        return False, "허용되지 않은 주소입니다."
    cmd = ("[Net.ServicePointManager]::SecurityProtocol="
           "[Net.SecurityProtocolType]::Tls12; "
           f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest}' -UseBasicParsing")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", cmd],
                           capture_output=True, text=True, timeout=600,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if not os.path.exists(dest):
        return False, (r.stderr or r.stdout or "내려받지 못했습니다.")[-400:]
    return True, ""


def 받은파일검사(path):
    """정말 zip 인지, 크기가 말이 되는지 본다. 아무 파일이나 실행하지 않는다."""
    try:
        크기 = os.path.getsize(path)
    except OSError as e:
        return False, f"{e}", None
    if 크기 < 100_000:
        return False, f"파일이 너무 작습니다 ({크기:,} 바이트)", None
    if 크기 > 200_000_000:
        return False, f"파일이 너무 큽니다 ({크기:,} 바이트)", None
    try:
        with open(path, "rb") as fh:
            if fh.read(2) != b"PK":
                return False, "압축 파일이 아닙니다", None
    except OSError as e:
        return False, f"{e}", None
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            이름들 = z.namelist()
            exe = [n for n in 이름들 if n.lower().endswith(".exe")]
            if not exe:
                return False, "압축 안에 설치 파일이 없습니다", None
            return True, "", (이름들, exe[0])
    except Exception as e:
        return False, f"압축을 열지 못했습니다: {e}", None


def inf로설치(폴더):
    """압축을 푼 폴더의 INF 를 드라이버 저장소에 등록한다.

    ★이것이 가장 확실하다 (2026-09-10 조사)
      설치 실행파일(setup exe)은 무인(/S) 옵션이 판마다 다르고 실패해도
      종료코드가 0 일 수 있다. 반면 `pnputil /add-driver ... /install` 은
      **드라이버 저장소에 실제로 등록**하고, 그 뒤 장치를 다시 훑으면 붙는다.
      Problem 28(드라이버 없음)은 이 방법으로 해결된다.
    """
    infs = []
    for 뿌리, _, 파일들 in os.walk(폴더):
        for f in 파일들:
            if f.lower().endswith(".inf") and "ftdi" in f.lower():
                infs.append(os.path.join(뿌리, f))
    if not infs:
        for 뿌리, _, 파일들 in os.walk(폴더):
            for f in 파일들:
                if f.lower().endswith(".inf"):
                    infs.append(os.path.join(뿌리, f))
    if not infs:
        return False, "압축 안에 INF 파일이 없습니다."
    성공, 기록 = 0, []
    for inf in infs[:6]:
        rc, msg = ps_runas("pnputil.exe", f"/add-driver \"{inf}\" /install")
        기록.append(f"{os.path.basename(inf)} → {rc}")
        if rc == 0:
            성공 += 1
    if 성공:
        ps_runas("pnputil.exe", "/scan-devices")
        return True, f"INF {성공}개를 등록했습니다 ({', '.join(기록)})"
    return False, f"INF 등록 실패 ({', '.join(기록)})"


def ftdi설치():
    임시 = tempfile.mkdtemp(prefix="ftdi_")
    마지막 = ""
    for url in FTDI_URLS:
        zip경로 = os.path.join(임시, os.path.basename(url))
        ok, err = 내려받기(url, zip경로)
        if not ok:
            마지막 = f"{url} → {err}"
            continue
        ok, err, info = 받은파일검사(zip경로)
        if not ok:
            마지막 = f"{url} → {err}"
            continue
        import zipfile
        with zipfile.ZipFile(zip경로) as z:
            z.extractall(임시)
        # ① INF 를 드라이버 저장소에 등록한다 (가장 확실하다)
        ok2, msg2 = inf로설치(임시)
        if ok2:
            import time as _t
            _t.sleep(3)
            if 드라이버붙었나("0403"):
                return True, msg2
            마지막 = msg2 + "  (등록했지만 아직 장치에 안 붙었습니다)"
        else:
            마지막 = msg2

        # ② 그래도 안 되면 제조사 설치 파일을 실행한다
        exe = os.path.join(임시, info[1])
        if os.path.exists(exe):
            rc, m1 = ps_runas(exe, "/S")
            import time as _t
            _t.sleep(4)
            if 드라이버붙었나("0403"):
                return True, f"설치 파일로 붙였습니다: {os.path.basename(exe)}"
            rc2, m2 = ps_runas(exe, "")     # 창을 띄워 사람이 진행
            _t.sleep(2)
            if 드라이버붙었나("0403"):
                return True, f"설치 창으로 붙였습니다: {os.path.basename(exe)}"
            마지막 += f" / 설치파일 코드 {rc}·{rc2}"
        # 압축을 푼 자리를 알려 준다 — 수동 지정에 쓸 수 있다
        마지막 += f"  [압축을 푼 곳: {임시}]"
        return False, 마지막
    return False, 마지막 or "내려받지 못했습니다."


def 브라우저로열기(url):
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Start-Process '{url}'"], timeout=30)
        return True
    except Exception:
        return False


def main():
    if not IS_WINDOWS:
        out(ok=False, step="os", error="윈도우에서만 쓸 수 있습니다.")
        return 0
    무엇 = sys.argv[1] if len(sys.argv) > 1 else "FTDI VCP"

    if 무엇 != "FTDI VCP":
        # FTDI 외의 칩은 공식 페이지를 열어 주는 데까지만 한다.
        # 배포 주소가 자주 바뀌어 자동 설치가 오히려 위험하다.
        page = CHIP_PAGES.get(무엇, FTDI_PAGE)
        브라우저로열기(page)
        out(ok=False, step="manual", page=page,
            error=f"{무엇} 드라이버는 받는 곳을 열어 드렸습니다. 설치 뒤 다시 실행하십시오.")
        return 0

    전 = 직렬장치상태("0403")

    ok, msg1 = 윈도우업데이트로시도("0403")
    if ok:
        out(ok=True, step="windows_update",
            message="윈도우가 드라이버를 붙였습니다. " + msg1[-150:])
        return 0

    # ① 이 안 됐다 — 공식 설치 파일로 진행한다
    ok, msg2 = ftdi설치()
    if ok:
        # ★설치 파일이 「실행됐다」와 「드라이버가 붙었다」는 다르다.
        #   여기서도 실제 상태로 확인한다.
        import time as _t
        _t.sleep(5)
        붙음 = 드라이버붙었나("0403")
        out(ok=True, step="vendor_installer", installed=붙음,
            message=msg2 + ("  드라이버가 붙었습니다." if 붙음
                            else "  아직 장치에 붙지 않았습니다 — USB 를 다시 꽂아 주십시오."),
            before=전, after=직렬장치상태("0403"))
        return 0

    브라우저로열기(FTDI_PAGE)
    out(ok=False, step="failed", page=FTDI_PAGE,
        brainco=BRAINCO_PAGE, brainco_sdk=BRAINCO_SDK,
        error=(f"자동 설치가 되지 않았습니다 — 직접 받아 설치해 주십시오. "
               f"통신 칩 드라이버 {FTDI_PAGE} · 로봇손 제조사 자료실 {BRAINCO_PAGE} "
               f"(윈도우 업데이트: {msg1[-120:]} / 공식 설치: {msg2})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
