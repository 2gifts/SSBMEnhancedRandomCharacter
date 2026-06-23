#!/usr/bin/env python3
"""Enhanced Random Character installer for Melee (Slippi / regular Dolphin).

Copies the Gecko codeset into your Dolphin user folder and turns cheats on.
No game files are touched.

Usage:
  python install.py                      # auto-detect Slippi Dolphin
  python install.py "D:\\Dolphin\\User"  # a specific Dolphin "User" folder

The file installed is GALE01r2.ini (Melee 1.02 is revision r2); it loads in
both Slippi Dolphin and regular Dolphin for a 1.02 ISO.

Uninstall: delete GameSettings\\GALE01r2.ini (restore the .erc-backup if one was
made). Re-run any time -- it's idempotent.
"""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INI = "GALE01r2.ini"
BACKUP_SUFFIX = ".erc-backup"


def find_src() -> Path:
    for cand in (HERE / "dist" / INI, HERE / INI):
        if cand.exists():
            return cand
    sys.exit(f"error: {INI} not found -- run this from the repo (it lives in dist/)")


def default_user() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "Slippi Launcher" / "netplay" / "User"
        if p.exists():
            return p
    return None


def enable_cheats(user: Path) -> None:
    cfg = user / "Config" / "Dolphin.ini"
    if not cfg.exists():
        print(f"  note: {cfg} not found -- turn on Config > General > Enable "
              "Cheats in Dolphin yourself")
        return
    lines = cfg.read_text(encoding="utf-8", errors="ignore").splitlines()
    out, i, n, placed = [], 0, len(lines), False
    while i < n:
        out.append(lines[i])
        if lines[i].strip().lower() == "[core]":
            i += 1
            section = []
            while i < n and not lines[i].strip().startswith("["):
                section.append(lines[i])
                i += 1
            if any(s.strip().lower().startswith("enablecheats") for s in section):
                section = ["EnableCheats = True"
                           if s.strip().lower().startswith("enablecheats") else s
                           for s in section]
            else:
                section.insert(0, "EnableCheats = True")
            out.extend(section)
            placed = True
            continue
        i += 1
    if not placed:
        out += ["[Core]", "EnableCheats = True"]
    cfg.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("  Enable Cheats set in Dolphin.ini")


def main() -> None:
    src = find_src()
    user = Path(sys.argv[1]) if len(sys.argv) > 1 else default_user()
    if user is None:
        sys.exit("error: could not find Slippi Dolphin. Pass your Dolphin 'User'"
                 " folder, e.g.:  python install.py \"D:\\Dolphin\\User\"")
    if not user.exists():
        sys.exit(f"error: folder does not exist: {user}")

    gs = user / "GameSettings"
    gs.mkdir(parents=True, exist_ok=True)
    dst = gs / INI
    if dst.exists():
        bak = dst.with_name(dst.name + BACKUP_SUFFIX)
        if not bak.exists():
            shutil.copy2(dst, bak)
            print(f"  backup: {bak.name}")
    shutil.copy2(src, dst)
    print(f"  installed {INI} -> {dst}")
    enable_cheats(user)
    print("Done. Launch Melee, go to VS Mode, and tap L on a character to test.")


if __name__ == "__main__":
    main()
