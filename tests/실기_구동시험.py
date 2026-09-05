#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 pi2jw
# Licensed under the Apache License, Version 2.0. See ../LICENSE
#
"""
================================================================================
 실기 구동 시험 — 로봇손이 명령대로 '실제로 움직였는가'를 증명한다
================================================================================

■ 왜 필요한가
   명령을 보냈다는 것과 로봇이 움직였다는 것은 다르다.
   전송 함수가 예외 없이 끝나도, 전원이 없거나 모터가 걸려 있으면 손은 그대로다.
   그래서 여기서는 **보낸 값과 로봇에서 되읽은 값을 대조**한다.

■ 무엇을 하는가
   1) 포트를 자동 탐색해 연결하고 장치 정보를 출력한다
   2) 저장소 프리셋 제스처를 하나씩 보내고, 매번 실제 위치를 되읽어 비교한다
   3) 마지막에 반드시 손을 펴고 포트를 닫는다

■ 실행
     sg dialout -c "./.venv/bin/python tests/실기_구동시험.py"
       ※ 재로그인을 했다면 sg 없이 그냥 실행해도 된다

■ 로봇이 응답하지 않을 때
   24V DC 어댑터부터 확인한다. USB 는 통신 전용이라 전원 없이는 응답하지 않는다.
   이때도 포트는 정상적으로 열리므로 원인을 찾기 어렵다.
================================================================================
"""

import argparse
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))
from hand_tracking_control import FINGER_NAMES, SdkBackend, N_FINGER  # noqa: E402

# 저장소 hand_keyboard.py 의 GESTURES 와 같은 값
# ─────────────────────────────────────────────────────────────────────────────
# 판정 기준 — 왜 '폄'과 '쥠'을 다르게 보는가
#
#   폄(0) 방향에는 아무 방해가 없다. 손가락이 벌어지는 쪽이므로 서로 부딪히지 않는다.
#   따라서 정확히 도달해야 하고, 못 하면 진짜 고장이다.
#   이 방향은 안전과도 직결된다(시작·종료 때 반드시 손을 편다).
#
#   쥠(1000) 방향은 다르다. 손가락끼리 물리적으로 맞닿는다.
#     · 엄지는 접힌 손가락 위에 얹혀 더 들어가지 못한다
#     · 주먹에서는 검지마저 엄지에 막힌다
#   사람 손도 똑같다. 주먹을 쥐어도 엄지가 손바닥까지 파고들지는 않는다.
#   그러므로 쥠 방향은 '목표까지 갔는가'가 아니라 '충분히 움직였는가'로 본다.
#
#   실측 근거(Revo2 Basic 오른손 실기, 2026-09-03):
#     방해가 없을 때  엄지만 쥠 → 988~990 도달  (목표 1000)
#     방해가 있을 때  주먹      → 엄지 636, 엄지보조 488, 검지 675
#   → 부분 도달의 하한을 400 으로 잡았다(실측 최저 488 보다 낮게).
# ─────────────────────────────────────────────────────────────────────────────
CLOSE_TARGET = 600      # 명령이 이 값 이상이면 '쥠' 방향으로 본다
PARTIAL_MIN = 400       # 쥠 방향에서 최소한 여기까지는 움직여야 정상


def judge(target, actual, tol):
    """보낸 값과 실제 위치를 대조한다. (통과 여부, 설명) 을 돌려준다."""
    bad, partial = [], []
    for i, (t, a) in enumerate(zip(target, actual)):
        if abs(a - t) <= tol:
            continue                                  # 정확히 도달
        if t >= CLOSE_TARGET and a >= PARTIAL_MIN:
            partial.append(f"{FINGER_NAMES[i]} {a}")  # 접촉으로 막힘 — 정상
        else:
            bad.append(f"{FINGER_NAMES[i]} 목표 {t} → 실제 {a}")
    if bad:
        return False, " / ".join(bad)
    if partial:
        return True, "나머지 축 정확 도달 / 접촉으로 막힌 축: " + ", ".join(partial)
    return True, f"전 축 정확 도달 (최대차 {max(abs(a-t) for t,a in zip(target,actual))})"


SEQUENCE = [
    ("손 펴기 (보)",   [0,    0,    0,    0,    0,    0]),
    ("주먹",           [1000, 1000, 1000, 1000, 1000, 1000]),
    ("브이 (가위)",    [1000, 1000, 0,    0,    1000, 1000]),
    ("엄지 척",        [0,    0,    1000, 1000, 1000, 1000]),
    ("가리키기",       [1000, 1000, 0,    1000, 1000, 1000]),
    ("반쯤 쥐기",      [500,  500,  500,  500,  500,  500]),
    ("손 펴기 (보)",   [0,    0,    0,    0,    0,    0]),
]


async def run(sdk_dir, tol, hold):
    backend = SdkBackend(sdk_dir=sdk_dir)
    revo2 = backend._resolve_sdk_dir()
    if revo2 not in sys.path:
        sys.path.insert(0, revo2)
    from bc_stark_sdk import main_mod as libstark
    from revo2_utils import open_modbus_revo2

    print("=" * 78)
    print(" 실기 구동 시험 — 보낸 값과 로봇 실제 위치를 대조한다")
    print("=" * 78)
    print(f"\n[1] 연결 (SDK: {revo2})")
    client, slave_id = await open_modbus_revo2()
    print(f"    slave_id {slave_id} (0x{slave_id:02X})")
    try:
        info = await client.get_device_info(slave_id)
        for k in ("serial_number", "hand_type", "hardware_type", "firmware_version"):
            v = getattr(info, k, None)
            if v is not None:
                print(f"    {k:<18} {v}")
    except Exception as e:
        print(f"    장치 정보 읽기 실패: {type(e).__name__}: {e}")

    await client.set_finger_unit_mode(slave_id, libstark.FingerUnitMode.Normalized)
    print("    단위 모드: Normalized (0~1000)")

    print(f"\n[2] 제스처 {len(SEQUENCE)}종 구동 및 되읽기 (허용 오차 {tol})")
    head = f"  {'제스처':<14}" + "".join(f"{n:>7}" for n in FINGER_NAMES) + "   판정"
    print(head)
    print("  " + "-" * (len(head) + 4))

    n_ok = n_ng = 0
    try:
        for name, target in SEQUENCE:
            await client.set_finger_positions_and_durations(
                slave_id, list(target), [400] * N_FINGER)
            await asyncio.sleep(hold)
            actual = list(await client.get_finger_positions(slave_id))
            ok, note = judge(target, actual, tol)
            n_ok += int(ok); n_ng += int(not ok)
            print(f"  {name:<14}" + "".join(f"{v:>7}" for v in target) + "   보냄")
            print(f"  {'':<14}" + "".join(f"{v:>7}" for v in actual)
                  + f"   {'통과' if ok else '실패'}  {note}")
    finally:
        print("\n[3] 안전 종료 — 손 펴기")
        await client.set_finger_positions_and_durations(
            slave_id, [0] * N_FINGER, [600] * N_FINGER)
        await asyncio.sleep(1.0)
        final = list(await client.get_finger_positions(slave_id))
        print(f"    최종 위치 {final}")
        libstark.modbus_close(client)
        print("    포트 닫음")

    print("\n" + "=" * 78)
    print(f" 결과: 통과 {n_ok}건 / 실패 {n_ng}건")
    if n_ng == 0:
        print(" 로봇이 명령대로 움직였다. (엄지가 접힌 손가락에 막히는 것은 기구적 한계)")
    print("=" * 78)
    return 0 if n_ng == 0 else 1


def main():
    ap = argparse.ArgumentParser(description="Revo2 실기 구동 시험")
    ap.add_argument("--sdk-dir", default=None, help="제조사 SDK 예제 폴더")
    ap.add_argument("--tol", type=int, default=60,
                    help="보낸 값과 실제 위치의 허용 오차 (기본 60). "
                         "모터는 기계적 한계·부하 때문에 정확히 도달하지 않는다")
    ap.add_argument("--hold", type=float, default=1.2,
                    help="각 자세를 유지하며 기다릴 시간(초)")
    args = ap.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(lambda l, c: None)
    try:
        rc = loop.run_until_complete(run(args.sdk_dir, args.tol, args.hold))
        loop.run_until_complete(asyncio.sleep(0.3))
        return rc
    finally:
        try:
            loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
