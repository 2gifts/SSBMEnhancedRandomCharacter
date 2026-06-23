"""Minimal GameCube ISO reader: extract the DOL and files, map RAM addresses
to DOL file offsets. GC discs are unencrypted, so this is plain offset math.

Disc layout (big-endian):
  0x0000  game id (6) + maker (2)
  0x0420  u32 dol_offset
  0x0424  u32 fst_offset
  0x0428  u32 fst_size

DOL header:
  0x00  u32 text_offset[7]
  0x1C  u32 data_offset[11]
  0x48  u32 text_address[7]
  0x64  u32 data_address[11]
  0x90  u32 text_size[7]
  0xAC  u32 data_size[11]
  0xD8  u32 bss_address, 0xDC u32 bss_size, 0xE0 u32 entry_point
"""
import struct
import sys


def be32(b, off):
    return struct.unpack_from(">I", b, off)[0]


class GCIso:
    def __init__(self, path):
        self.f = open(path, "rb")
        hdr = self.f.read(0x440)
        self.game_id = hdr[:6].decode("ascii", "replace")
        self.dol_offset = be32(hdr, 0x420)
        self.fst_offset = be32(hdr, 0x424)
        self.fst_size = be32(hdr, 0x428)

    def read(self, off, size):
        self.f.seek(off)
        return self.f.read(size)

    # ---- DOL ----
    def dol_header(self):
        return self.read(self.dol_offset, 0x100)

    def dol_sections(self):
        """[(kind, idx, file_off_in_iso, ram_addr, size)] for non-empty sections."""
        h = self.dol_header()
        out = []
        for i in range(7):
            off, addr, size = be32(h, i * 4), be32(h, 0x48 + i * 4), be32(h, 0x90 + i * 4)
            if size:
                out.append(("text", i, self.dol_offset + off, addr, size))
        for i in range(11):
            off, addr, size = be32(h, 0x1C + i * 4), be32(h, 0x64 + i * 4), be32(h, 0xAC + i * 4)
            if size:
                out.append(("data", i, self.dol_offset + off, addr, size))
        return out

    def read_ram(self, ram_addr, size):
        """Read bytes as they would appear at a RAM address (DOL static map)."""
        for kind, i, foff, addr, ssize in self.dol_sections():
            if addr <= ram_addr and ram_addr + size <= addr + ssize:
                return self.read(foff + (ram_addr - addr), size)
        raise ValueError(f"address {ram_addr:#x} (+{size:#x}) not in any DOL section")

    # ---- FST (file table) ----
    def files(self):
        """[(path, file_offset, size)]"""
        fst = self.read(self.fst_offset, self.fst_size)
        n_entries = be32(fst, 0x8)
        str_base = n_entries * 12
        out = []
        stack = []  # (dir_name, end_index)
        i = 1
        while i < n_entries:
            flags = fst[i * 12]
            name_off = be32(fst, i * 12) & 0xFFFFFF
            name = fst[str_base + name_off: fst.index(b"\0", str_base + name_off)].decode(
                "ascii", "replace")
            while stack and i >= stack[-1][1]:
                stack.pop()
            if flags == 1:  # directory
                end = be32(fst, i * 12 + 8)
                stack.append((name, end))
            else:
                path = "/".join([d for d, _ in stack] + [name])
                out.append((path, be32(fst, i * 12 + 4), be32(fst, i * 12 + 8)))
            i += 1
        return out

    def extract(self, path_wanted, dest):
        for path, off, size in self.files():
            if path == path_wanted:
                data = self.read(off, size)
                with open(dest, "wb") as g:
                    g.write(data)
                return size
        raise FileNotFoundError(path_wanted)


def main():
    iso = GCIso(sys.argv[1])
    print("game:", iso.game_id, "dol@", hex(iso.dol_offset))
    for kind, i, foff, addr, size in iso.dol_sections():
        print(f"  {kind}{i}: iso+{foff:#x} -> {addr:#010x} +{size:#x}")
    if len(sys.argv) > 2 and sys.argv[2] == "ls":
        for path, off, size in iso.files():
            print(f"  {path}  @{off:#x} +{size:#x}")


if __name__ == "__main__":
    main()
