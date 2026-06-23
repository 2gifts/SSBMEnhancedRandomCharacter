#!/usr/bin/env python3
"""Read (and optionally poke) Dolphin's emulated Wii RAM from outside the
process — the same technique Dolphin Memory Engine uses.

Locates MEM1 (0x80000000, 32MB) and MEM2 (0x90000000, 64MB) inside a running
Dolphin.exe by scanning its mapped regions and validating the game ID string
at MEM1+0.

Usage:
  python dolmem.py read  <addr-hex> <size>          hex dump
  python dolmem.py read32 <addr-hex>                one word
  python dolmem.py write <addr-hex> <bytes-hex>     poke bytes (testing only)
  python dolmem.py find  <bytes-hex> [mem1|mem2]    search, prints Wii addresses
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
MEM1_SIZE = 0x02000000
MEM2_SIZE = 0x04000000

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("PartitionId", wt.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


def find_dolphin_pids():
    arr = (wt.DWORD * 4096)()
    needed = wt.DWORD()
    psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed))
    pids = []
    for i in range(needed.value // 4):
        pid = arr[i]
        h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h:
            continue
        name = ctypes.create_unicode_buffer(260)
        if psapi.GetModuleBaseNameW(h, None, name, 260):
            if name.value.lower() in ("dolphin.exe", "dolphinqt2.exe", "dolphin-emu.exe",
                                      "slippi dolphin.exe", "slippi_dolphin.exe"):
                pids.append(pid)
        k32.CloseHandle(h)
    return pids


class DolphinMem:
    def __init__(self, pid=None):
        pids = [pid] if pid else find_dolphin_pids()
        if not pids:
            raise SystemExit("no running Dolphin.exe found")
        self.h = None
        for p in pids:
            h = k32.OpenProcess(
                PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
                | PROCESS_QUERY_INFORMATION,
                False,
                p,
            )
            if h and self._locate(h):
                self.h = h
                self.pid = p
                return
            if h:
                k32.CloseHandle(h)
        raise SystemExit("found Dolphin but no emulated RAM (game not running?)")

    def _rpm(self, h, addr, size):
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
            return None
        return buf.raw[: got.value]

    def _locate(self, h):
        self.mem1 = self.mem2 = None
        addr = 0
        mbi = MBI()
        while k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            base = mbi.BaseAddress or 0
            if mbi.State == 0x1000 and mbi.Type == 0x40000:  # MEM_COMMIT, MEM_MAPPED
                if mbi.RegionSize == MEM2_SIZE and self.mem2 is None:
                    self.mem2 = base
                if mbi.RegionSize == MEM1_SIZE and self.mem1 is None:
                    head = self._rpm(h, base, 8)
                    # game ID at MEM1+0; first byte is sometimes zeroed by loaders
                    if head and (head[:6].isalnum() or head[1:6].isalnum()):
                        self.mem1 = base
            addr = base + mbi.RegionSize
            if addr >= 0x7FFFFFFFFFFF:
                break
        return self.mem1 is not None

    def _host(self, wii_addr, size):
        if 0x80000000 <= wii_addr and wii_addr + size <= 0x80000000 + MEM1_SIZE:
            return self.mem1 + (wii_addr - 0x80000000)
        if 0x90000000 <= wii_addr and wii_addr + size <= 0x90000000 + MEM2_SIZE:
            if self.mem2 is None:
                raise SystemExit("MEM2 not located")
            return self.mem2 + (wii_addr - 0x90000000)
        raise SystemExit(f"address out of range: {wii_addr:#x}")

    def read(self, wii_addr, size):
        data = self._rpm(self.h, self._host(wii_addr, size), size)
        if data is None:
            raise SystemExit(f"read failed at {wii_addr:#x}")
        return data

    def read32(self, wii_addr):
        return struct.unpack(">I", self.read(wii_addr, 4))[0]

    def write(self, wii_addr, data):
        host = self._host(wii_addr, len(data))
        written = ctypes.c_size_t()
        if not k32.WriteProcessMemory(
            self.h, ctypes.c_void_p(host), data, len(data), ctypes.byref(written)
        ):
            raise SystemExit(f"write failed at {wii_addr:#x}")

    def find(self, needle, region="mem1"):
        base_wii, size = (
            (0x80000000, MEM1_SIZE) if region == "mem1" else (0x90000000, MEM2_SIZE)
        )
        hits = []
        chunk = 0x100000
        for off in range(0, size, chunk):
            data = self.read(base_wii + off, min(chunk + len(needle), size - off))
            start = 0
            while True:
                i = data.find(needle, start)
                if i < 0:
                    break
                hits.append(base_wii + off + i)
                start = i + 1
        # de-dup overlap hits
        return sorted(set(hits))


def hexdump(addr, data):
    for i in range(0, len(data), 16):
        row = data[i : i + 16]
        h = " ".join(f"{b:02x}" for b in row)
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"{addr+i:08X}  {h:<47}  {a}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    m = DolphinMem()
    if cmd == "read":
        addr = int(sys.argv[2], 16)
        size = int(sys.argv[3], 0)
        hexdump(addr, m.read(addr, size))
    elif cmd == "read32":
        print(f"{m.read32(int(sys.argv[2], 16)):08X}")
    elif cmd == "write":
        m.write(int(sys.argv[2], 16), bytes.fromhex(sys.argv[3]))
        print("ok")
    elif cmd == "find":
        region = sys.argv[3] if len(sys.argv) > 3 else "mem1"
        for a in m.find(bytes.fromhex(sys.argv[2]), region):
            print(f"{a:08X}")
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
