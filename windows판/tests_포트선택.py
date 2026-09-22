#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""포트 고르기가 제대로 되는지 검사한다 (로봇 없이).

★2026-09-10 j2w 가 막힌 지점이 바로 여기다.
  더블클릭으로는 `--port COM3` 을 줄 방법이 없어서, COM 번호를 아는 것과
  상관없이 실행이 안 됐다. 그래서 프로그램이 스스로 찾고 고르게 만들었고,
  그 길이 실제로 도는지 여기서 확인한다.
"""
import builtins
import importlib.util
import io
import contextlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("setup_mod", os.path.join(HERE, "_setup.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.LOGF = os.path.join("/tmp", "_시험기록.txt")

P = F = 0
def ok(t):
    global P; P += 1; print(f"  \033[32m✓\033[0m {t}")
def ng(t):
    global F; F += 1; print(f"  \033[31m✗\033[0m {t}")

def 포트를(목록, ok_=True, err=""):
    m.read_ports = lambda vpy: (ok_, 목록, err)

def 입력을(*답):
    it = iter(답)
    builtins.input = lambda *a, **k: next(it, "")

print("\n1. 포트가 하나면 묻지 않고 그것을 쓴다")
포트를(["COM3"]); 입력을()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    r = m.choose_port("py")
ok("COM3 자동 선택") if r == "COM3" else ng(f"고른 값 {r}")
ok("사람에게 묻지 않았다") if "번호 [" not in buf.getvalue() else ng("하나뿐인데 물었다")

print("\n2. 여러 개면 번호를 보여 주고 고르게 한다")
포트를(["COM1", "COM3", "COM7"]); 입력을("2")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    r = m.choose_port("py")
out = buf.getvalue()
ok("2번을 고르면 COM3") if r == "COM3" else ng(f"고른 값 {r}")
ok("세 개를 모두 보여 준다") if all(x in out for x in ("COM1", "COM3", "COM7")) else ng("목록이 안 보인다")
ok("가상 포트가 섞일 수 있다고 알린다") if "가상" in out else ng("안내가 없다")

print("\n3. 그냥 엔터를 치면 1번을 쓴다 (가장 흔한 조작)")
포트를(["COM1", "COM3"]); 입력을("")
with contextlib.redirect_stdout(io.StringIO()):
    r = m.choose_port("py")
ok("엔터 → COM1") if r == "COM1" else ng(f"고른 값 {r}")

print("\n4. 엉뚱한 값을 넣어도 멈추지 않는다")
포트를(["COM1", "COM3"]); 입력을("9", "abc", "2")
with contextlib.redirect_stdout(io.StringIO()):
    r = m.choose_port("py")
ok("잘못 넣어도 다시 묻고, 결국 COM3") if r == "COM3" else ng(f"고른 값 {r}")

print("\n5. --port 를 직접 주면 그것을 쓴다 (찾지 않는다)")
불렸다 = {"v": False}
def 찾음(vpy):
    불렸다["v"] = True
    return True, ["COM9"], ""
m.read_ports = 찾음
with contextlib.redirect_stdout(io.StringIO()):
    r = m.choose_port("py", "COM5")
ok("지정한 COM5 를 쓴다") if r == "COM5" else ng(f"고른 값 {r}")
ok("지정했으면 찾지 않는다") if not 불렸다["v"] else ng("지정했는데도 찾았다")

print("\n6. 포트가 없으면 24V 부터 안내하고 멈춘다")
포트를([]); 입력을("")
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        m.choose_port("py")
    ng("포트가 없는데 그냥 진행했다")
except SystemExit:
    out = buf.getvalue()
    ok("멈춘다")
    ok("24V 를 가장 먼저 안내한다") if out.index("24V") < out.index("USB 케이블") else ng("안내 순서가 뒤바뀌었다")
    ok("기록 파일 위치를 알려 준다") if "실행기록" in out or m.LOGF.split("/")[-1] in out else ng("기록 안내가 없다")

print("\n7. 포트 조회 자체가 실패해도 죽지 않는다 (SDK 가 스스로 찾을 수 있다)")
포트를([], ok_=False, err="ImportError: 어쩌구")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    r = m.choose_port("py")
ok("None 을 돌려주고 계속 간다") if r is None else ng(f"돌려준 값 {r}")
ok("무엇이 실패했는지 화면에 남긴다") if "ImportError" in buf.getvalue() else ng("이유가 안 보인다")

print(f"\n결과  통과 {P}건 · 실패 {F}건")
sys.exit(1 if F else 0)
