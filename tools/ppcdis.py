"""Disassemble a RAM address range straight out of the ISO's DOL.

Usage: python dis.py <iso> <start_hex> <end_hex>
"""
import sys

from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
from gciso import GCIso


def disasm(iso_path, start, end):
    iso = GCIso(iso_path)
    code = iso.read_ram(start, end - start)
    cs = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    cs.skipdata = True  # don't stop on data words
    for insn in cs.disasm(code, start):
        yield insn


def main():
    iso_path, start, end = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
    for insn in disasm(iso_path, start, end):
        b = insn.bytes.hex()
        print(f"{insn.address:08X}  {b}  {insn.mnemonic:10s} {insn.op_str}")


if __name__ == "__main__":
    main()
