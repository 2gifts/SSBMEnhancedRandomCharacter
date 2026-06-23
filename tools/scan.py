"""Scan the DOL for (a) bl/b branches to a target, (b) cmplwi rX, imm sites
within a range. Usage:
  python scan.py <iso> calls <target_hex> [lo hi]
  python scan.py <iso> cmplwi <imm_hex> <lo> <hi>
"""
import struct
import sys

from gciso import GCIso


def words(iso, lo, hi):
    raw = iso.read_ram(lo, hi - lo)
    for i in range(0, len(raw) - 3, 4):
        yield lo + i, struct.unpack_from(">I", raw, i)[0]


def main():
    iso = GCIso(sys.argv[1])
    mode = sys.argv[2]
    if mode == "calls":
        target = int(sys.argv[3], 16)
        lo = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x80005940
        hi = int(sys.argv[5], 16) if len(sys.argv) > 5 else 0x803B7240
        for addr, w in words(iso, lo, hi):
            if (w >> 26) == 18:  # I-form branch (b/bl/ba/bla)
                li = w & 0x03FFFFFC
                if li & 0x02000000:
                    li -= 0x04000000
                dest = li if (w & 2) else addr + li  # AA bit
                if dest == target:
                    kind = "bl" if (w & 1) else "b"
                    print(f"{addr:08X}  {kind} -> {target:08X}")
    elif mode == "cmplwi":
        imm = int(sys.argv[3], 16)
        lo, hi = int(sys.argv[4], 16), int(sys.argv[5], 16)
        for addr, w in words(iso, lo, hi):
            # cmplwi crD, rA, imm  = opcode 10 (0x28xxxxxx); cmpwi = opcode 11
            op = w >> 26
            if op in (10, 11) and (w & 0xFFFF) == imm:
                ra = (w >> 16) & 0x1F
                print(f"{addr:08X}  {'cmplwi' if op == 10 else 'cmpwi'} r{ra}, {imm:#x}")


if __name__ == "__main__":
    main()
