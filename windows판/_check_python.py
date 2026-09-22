#!/usr/bin/env python3
"""이 파이썬이 쓸 만한지 확인한다. 쓸 만하면 판 번호를 찍고 0 을 돌려준다."""
import sys

MIN_VER = (3, 9)
MAX_VER = (3, 15)


def main():
    is_64bit = sys.maxsize.bit_length() >= 63
    ver = sys.version_info[:2]
    if not (is_64bit and MIN_VER <= ver < MAX_VER):
        return 1
    sys.stdout.write(sys.version.split()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
