"""Bake the RandomList hooks directly into an ISO's DOL (console route —
no GCT/codehandler involvement, so it coexists cleanly with Slippi
Nintendont's own injected codes).

For each hook: a `b cave` replaces the instruction at the injection site;
the cave holds the C2 body (which re-emits the original instruction)
followed by `b site+4`. Caves are allocated from MCM's "Tournament Mode
Region" (DOL offset 0x18DCC0..0x197B30 — community-standard free space;
vanilla Tournament Mode becomes unusable, which is acceptable).

Usage: python dolpatch.py <src.iso> <out.iso>
"""
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from build_codes import all_hooks  # noqa: E402
from gciso import GCIso  # noqa: E402

CAVE_DOL_START = 0x18DCC0    # DOL file offset (Tournament Mode Region)
CAVE_DOL_END = 0x197B30


def b_word(src, dst, link=False):
    rel = (dst - src) & 0x03FFFFFC
    return 0x48000000 | rel | (1 if link else 0)


def main():
    src, out = sys.argv[1], sys.argv[2]
    shutil.copyfile(src, out)
    iso = GCIso(out)

    # map the cave (a DOL file offset) to its RAM address + ISO offset
    cave_ram = None
    for kind, i, foff, addr, ssize in iso.dol_sections():
        dol_off_lo = foff - iso.dol_offset
        if dol_off_lo <= CAVE_DOL_START < dol_off_lo + ssize:
            cave_ram = addr + (CAVE_DOL_START - dol_off_lo)
            break
    if cave_ram is None:
        raise SystemExit("cave region not inside a DOL section")
    print(f"cave: DOL+{CAVE_DOL_START:#x} = RAM {cave_ram:#010x}, "
          f"{CAVE_DOL_END - CAVE_DOL_START:#x} bytes")

    def ram_to_iso(ram):
        for kind, i, foff, addr, ssize in iso.dol_sections():
            if addr <= ram < addr + ssize:
                return foff + (ram - addr)
        raise SystemExit(f"{ram:#x} not in DOL")

    f = open(out, "r+b")
    pos = cave_ram
    total = 0
    for name, addr, body in all_hooks():
        orig = struct.unpack(">I", iso.read_ram(addr, 4))[0]
        # write the body + branch-back at the cave position
        words = list(body) + [b_word(pos + len(body) * 4, addr + 4)]
        f.seek(ram_to_iso(pos))
        f.write(b"".join(struct.pack(">I", w) for w in words))
        # write the branch into the cave at the hook site
        f.seek(ram_to_iso(addr))
        f.write(struct.pack(">I", b_word(addr, pos)))
        print(f"  {name}: {addr:#010x} (was {orig:08X}) -> cave "
              f"{pos:#010x} ({len(words)} words)")
        pos += len(words) * 4
        total += len(words) * 4
        if pos - cave_ram > (CAVE_DOL_END - CAVE_DOL_START):
            raise SystemExit("cave overflow")
    f.close()
    print(f"total cave usage: {total:#x} bytes; patched -> {out}")


if __name__ == "__main__":
    main()
