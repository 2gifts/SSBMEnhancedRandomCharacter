"""Closed-loop CSS driver: SendInput keys + memory verification.

Every action verifies its effect in emulated RAM and retries, so no
flaked keypress can corrupt a test run. Import and call, or run:
  python drive.py status
  python drive.py moveto <x> <y> [port]
  python drive.py tap <key> ...
"""
import ctypes
import struct
import sys
import time

from dolmem import DolphinMem

user32 = ctypes.windll.user32

# ---- SendInput ----
VK = {'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
      'x': 0x58, 'z': 0x5A, 'q': 0x51, 'w': 0x57, 'enter': 0x0D,
      'u': 0x55, 'o': 0x4F, 'y': 0x59, 'r': 0x52, 'n': 0x4E, 'v': 0x56,
      'comma': 0xBC}
EXTENDED = {'up', 'down', 'left', 'right'}

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _key_event(name, up):
    vk = VK[name]
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = 0x0001 if name in EXTENDED else 0
    if up:
        flags |= 0x0002
    user32.keybd_event(vk, scan, flags, 0)


def key_down(name):
    _key_event(name, False)


def key_up(name):
    _key_event(name, True)


def hold(name, dur=0.1):
    key_down(name)
    time.sleep(dur)
    key_up(name)
    time.sleep(0.05)


def focus_dolphin():
    import ctypes.wintypes as wt
    target = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        # the RENDER window is titled exactly 'Dolphin' (or 'Dolphin 5.0...');
        # 'Faster Melee - Slippi (x.y.z)' is the game-list/main window
        if buf.value == 'Dolphin' and user32.IsWindowVisible(hwnd):
            target.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    if not target:
        raise SystemExit('no Dolphin render window found')
    hwnd = target[0]
    # Alt-tap unlocks SetForegroundWindow when another app holds focus
    user32.keybd_event(0x12, 0, 0, 0)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.3)
    fg = user32.GetForegroundWindow()
    if fg != hwnd:
        user32.ShowWindow(hwnd, 6)   # minimize/restore cycle as fallback
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)


# ---- memory model ----
SC = 0x804D6AA0
DOORS = 0x803F0DFC
m = DolphinMem()


def r8(a):
    return m.read(a, 1)[0]


def rf(a):
    return struct.unpack('>f', m.read(a, 4))[0]


def hand(port=0):
    p = m.read32(0x804A0BC0 + port * 4)
    return rf(p + 0xC), rf(p + 0x10), r8(p + 5)


def coin(port=0):
    p = m.read32(0x804A0BD0 + port * 4)
    return rf(p + 8), rf(p + 0xC)


def sel(port=0):
    return r8(DOORS + port * 0x24 + 0xE)


def ckind(port=0):
    cssdata = m.read32(0x804D6CB0)
    return r8(cssdata + 0x70 + port * 0x24)


def flag(port=0):
    return r8(SC + 0x30 + port)


def lst(port=0):
    base = SC + 0x40 + port * 0x30
    n = r8(base)
    en = m.read(base + 1, 47)
    return n, [i for i, v in enumerate(en) if v]


# cached params (new RLV3 layout)
def p_count():
    return m.read32(SC + 0x08)


def p_selnone():
    return m.read32(SC + 0x10)


def p_cknone():
    return m.read32(SC + 0x14)


def p_icons():
    return m.read32(SC + 0x0C)


def p_isvan():
    return m.read32(SC + 0x18)


def dbg():
    return m.read32(SC + 0x120), m.read32(SC + 0x124)


def ready():
    return r8(0x804D6CF7)


def coin_held(port=0):
    p = m.read32(0x804A0BD0 + port * 4)
    return r8(p + 5) if p else None


def coin_hidden(port=0):
    # toggle hook hides jobj via gobj; check jobj flags bit
    ptr = m.read32(0x804A0BD0 + port * 4)
    g = m.read32(ptr) if ptr else 0
    if not (0x80000000 <= g < 0x81800000):
        return None
    j = m.read32(g + 0x28)
    if not (0x80000000 <= j < 0x81800000):
        return None
    return bool(m.read32(j + 4) & 0x10)


def status(port=0):
    hx, hy, hst = hand(port)
    cx, cy = coin(port)
    a, ar = dbg()
    print(f'P{port+1} hand=({hx:.1f},{hy:.1f}) st={hst} coin=({cx:.1f},{cy:.1f}) '
          f'hidden={coin_hidden(port)} sel={sel(port):#x} ck={ckind(port):#x} '
          f'flag={flag(port)} list={lst(port)} dbgA={a} dbgArm={ar}')


P2_DIR = {'left': 'y', 'right': 'r', 'up': 'u', 'down': 'o'}


def move_to(tx, ty, port=0, tol=0.8, timeout=12):
    """Closed-loop hand move with short key bursts."""
    keymap = P2_DIR if port == 1 else {k: k for k in
                                       ('left', 'right', 'up', 'down')}
    keys = {'left': False, 'right': False, 'up': False, 'down': False}
    t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            hx, hy, _ = hand(port)
            dx, dy = tx - hx, ty - hy
            if abs(dx) <= tol and abs(dy) <= tol:
                for k, on in keys.items():
                    if on:
                        key_up(keymap[k])
                        keys[k] = False
                time.sleep(0.1)
                hx, hy, _ = hand(port)
                if abs(tx - hx) <= tol and abs(ty - hy) <= tol:
                    return True
                continue
            want = {
                'left': dx < -tol, 'right': dx > tol,
                'up': dy > tol, 'down': dy < -tol,
            }
            for k in keys:
                if want[k] and not keys[k]:
                    key_down(keymap[k])
                    keys[k] = True
                elif not want[k] and keys[k]:
                    key_up(keymap[k])
                    keys[k] = False
            time.sleep(0.02)
        return False
    finally:
        for k, on in keys.items():
            if on:
                key_up(keymap[k])


def press_verify(key, check, retries=6, dur=0.12, settle=0.25):
    """Tap key until check() flips true. check is called after a settle."""
    for _ in range(retries):
        hold(key, dur)
        time.sleep(settle)
        if check():
            return True
    return False


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'status':
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        status(port)
    elif cmd == 'moveto':
        focus_dolphin()
        tx, ty = float(sys.argv[2]), float(sys.argv[3])
        port = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        ok = move_to(tx, ty, port)
        print('moved' if ok else 'TIMEOUT')
        status(port)
    elif cmd == 'tap':
        focus_dolphin()
        for k in sys.argv[2:]:
            hold(k, 0.12)
            time.sleep(0.3)
        status(0)
