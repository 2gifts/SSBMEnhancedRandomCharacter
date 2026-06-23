"""Tiny PPC assembler + Gecko C2 code emitter for our hooks/probes.

Only the handful of instruction forms we use. All big-endian.
"""


def lis(rt, imm):       return 0x3C000000 | (rt << 21) | (imm & 0xFFFF)
def ori(ra, rs, imm):   return 0x60000000 | (rs << 21) | (ra << 16) | (imm & 0xFFFF)
def lwz(rt, d, ra):     return 0x80000000 | (rt << 21) | (ra << 16) | (d & 0xFFFF)
def stw(rs, d, ra):     return 0x90000000 | (rs << 21) | (ra << 16) | (d & 0xFFFF)
def lbz(rt, d, ra):     return 0x88000000 | (rt << 21) | (ra << 16) | (d & 0xFFFF)
def stb(rs, d, ra):     return 0x98000000 | (rs << 21) | (ra << 16) | (d & 0xFFFF)
def lhz(rt, d, ra):     return 0xA0000000 | (rt << 21) | (ra << 16) | (d & 0xFFFF)
def addi(rt, ra, imm):  return 0x38000000 | (rt << 21) | (ra << 16) | (imm & 0xFFFF)
def nop():              return 0x60000000
def raw(word):          return word


def c2(addr, words):
    """Emit a Gecko C2 (insert ASM) code as INI lines. The final word of the
    final line must be 0x00000000 — the codehandler writes the branch-back
    there. Odd instruction count: last line = [insn, 0]. Even: add [nop, 0]."""
    ws = list(words)
    if len(ws) % 2 == 0:
        ws.append(nop())
    ws.append(0)
    lines = [f"C2{addr & 0xFFFFFF:06X} {len(ws)//2:08X}"]
    for i in range(0, len(ws), 2):
        lines.append(f"{ws[i]:08X} {ws[i+1]:08X}")
    return lines


def emit_ini(codes, path):
    """codes: list of (name, [ini lines])"""
    out = ["[Gecko]"]
    for name, lines in codes:
        out.append(f"${name}")
        out.extend(lines)
    out.append("[Gecko_Enabled]")
    for name, _ in codes:
        out.append(f"${name}")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")


# ---- extended ops ----
def cmplwi(ra, imm):    return 0x28000000 | (ra << 16) | (imm & 0xFFFF)
def cmpwi(ra, imm):     return 0x2C000000 | (ra << 16) | (imm & 0xFFFF)
def cmpw(ra, rb):       return 0x7C000000 | (ra << 16) | (rb << 11)
def mulli(rt, ra, imm): return 0x1C000000 | (rt << 21) | (ra << 16) | (imm & 0xFFFF)
def lbzx(rt, ra, rb):   return 0x7C0000AE | (rt << 21) | (ra << 16) | (rb << 11)
def stbx(rs, ra, rb):   return 0x7C0001AE | (rs << 21) | (ra << 16) | (rb << 11)
def lwzx(rt, ra, rb):   return 0x7C00002E | (rt << 21) | (ra << 16) | (rb << 11)
def xori(ra, rs, imm):  return 0x68000000 | (rs << 21) | (ra << 16) | (imm & 0xFFFF)
def andi_(ra, rs, imm): return 0x70000000 | (rs << 21) | (ra << 16) | (imm & 0xFFFF)
def add(rt, ra, rb):    return 0x7C000214 | (rt << 21) | (ra << 16) | (rb << 11)
def mr(ra, rs):         return 0x7C000378 | (rs << 21) | (ra << 16) | (rs << 11)
def orr(ra, rs, rb):    return 0x7C000378 | (rs << 21) | (ra << 16) | (rb << 11)
def mtctr(rs):          return 0x7C0903A6 | (rs << 21)
def bctrl():            return 0x4E800421
def rlwinm(ra, rs, sh, mb, me):
    return 0x54000000 | (rs << 21) | (ra << 16) | (sh << 11) | (mb << 6) | (me << 1)
def clrlwi(ra, rs, n):  return rlwinm(ra, rs, 0, n, 31)
def lfs(frt, d, ra):    return 0xC0000000 | (frt << 21) | (ra << 16) | (d & 0xFFFF)
def fcmpo(fra, frb):    return 0xFC000040 | (fra << 16) | (frb << 11)  # cr0

# label-based branches: emit ('b', cond, 'label') placeholders, resolve in asm()
def b(label):    return ('b', None, label)
def beq(label):  return ('bc', 0x41820000, label)
def bne(label):  return ('bc', 0x40820000, label)
def blt(label):  return ('bc', 0x41800000, label)
def bgt(label):  return ('bc', 0x41810000, label)
def ble(label):  return ('bc', 0x40810000, label)
def bge(label):  return ('bc', 0x40800000, label)
def label(name): return ('label', name)


def asm(items):
    """Two-pass assemble: items = ints | branch tuples | ('label', name).
    Returns list of u32 words."""
    # pass 1: addresses
    addr = 0
    labels = {}
    for it in items:
        if isinstance(it, tuple) and it[0] == 'label':
            labels[it[1]] = addr
        else:
            addr += 4
    # pass 2: emit
    out = []
    addr = 0
    for it in items:
        if isinstance(it, tuple):
            if it[0] == 'label':
                continue
            kind, opbase, target = it
            rel = labels[target] - addr
            if kind == 'b':
                out.append(0x48000000 | (rel & 0x03FFFFFC))
            else:
                assert -0x8000 <= rel <= 0x7FFF, f"bc out of range to {target}"
                out.append(opbase | (rel & 0xFFFC))
        else:
            out.append(it)
        addr += 4
    return out


def emit_gct(codes, path):
    """Binary GCT for Nintendont/Gecko OS: magic, all code lines, terminator."""
    import struct as _s
    out = [0x00D0C0DE, 0x00D0C0DE]
    for _name, lines in codes:
        for ln in lines:
            a, b = ln.split()
            out.append(int(a, 16))
            out.append(int(b, 16))
    out += [0xF0000000, 0x00000000]
    with open(path, "wb") as f:
        for w in out:
            f.write(_s.pack(">I", w))


def cmplw(ra, rb):      # cmplw cr0, rA, rB (logical compare)
    return 0x7C000040 | (ra << 16) | (rb << 11)
