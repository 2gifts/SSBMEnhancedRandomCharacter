# Verified addresses — Melee NTSC 1.02 (GALE01)

All values below were extracted from the user's ISO (`SSBMv102.iso`) by direct
DOL disassembly (`tools/ppcdis.py`, `tools/scan.py`) on 2026-06-10, cross-checked
against doldecomp/melee. "Live ✓" marks values additionally confirmed against a
running Slippi Dolphin.

## Register bases (set in __init_registers @ 0x80005340)
| reg | value |
|---|---|
| r2 (rtoc) | `0x804DF9E0` |
| r13 (sdata) | `0x804DB6A0` |

## The roll core — mnCharSel_8025FB50(door, arg1)
```
8025FB64  r27 = door (param r3), r26 = arg1
8025FB6C  r30 = 0x803F0A48 (mnCharSel static base)
8025FB70  li r3, 0x19          ← roll loop head
8025FB74  bl 0x80380580        ← HSD_Randi  ***HOOK A SITE***
8025FB78  r31 = r3 (icon idx) ; r29 = idx*0x1C
8025FB84  lbz r0, 0xDE(r30+r29) ; cmplwi 0 ; beq 8025FB70   (retry while locked)
8025FB90  loop exit: 1P remap via r13-0x49AF/-0x49B0, door count r13-0x49AB
8025FBC4  CSSData = lwz(r13-0x49F0) ; players[p].c_kind = stb +0x70 + p*0x24
```
**Hook A** replaces the `bl HSD_Randi` at `0x8025FB74`: return chosen icon idx
in r3. The outer loop retries locked icons for us. ABI scratch (r0, r3–r12,
LR, CTR) is free — it's a call site. r27=door, r30=0x803F0A48 live registers.
If our list pick is locked (state==0 @ icons[idx]+2), fall back to
HSD_Randi(0x19) for that attempt — never hang.

## Callers of 8025FB50 (all inside CursorThink; scan: complete DOL)
| site | meaning (decomp) |
|---|---|
| `0x80260584` | controller unplugged, fallback roll |
| `0x802605E0` | controller unplugged, no selection |
| `0x80260AE0` | **side-drop random** (r3 = r19 = door, r4 = 0) |
| `0x80261B54` | door toggled to CPU |

No other callers exist — one hook covers everything. (1P-mode opponent roll
uses a different path; intentionally vanilla.)

## Side-drop detection (inside CursorThink, 0x802609F4..0x80260AD4)
- Gate: A press (`rlwinm. r21, r28, 0, 23, 23` = mask 0x100).
- Coin position: `p = *(0x804A0BD0 + door*4)`; X = `*(p+0x8)` (f32), Y = `*(p+0xC)`.
- Window floats (rtoc r2 = 0x804DF9E0):
  - Y ∈ (−1.0 [r2−0x3534], 6.0 [r2−0x3538])
  - left strip X ∈ (−30.0 [r2−0x3530], −24.4 [r2−0x352C])
  - right strip X ∈ (24.4 [r2−0x3528], 30.2 [r2−0x3524])
- Then a fully-unlocked check: count icons with state ≥ 2 must equal 0x19
  (side-drop random only exists with everything unlocked) → `bl 8025FB50`.

## CursorThink (0x802602A0) prologue facts
- r26 = `0x804A0BC0`, r30 = `0x803F0A48`, r19 = door (loop var).
- Pad array: `0x804C20BC` (HSD_PadCopyStatus), stride 0x44/port: held u32 +0x0,
  pressed-this-frame u32 +0x8, stick s8 +0x18/+0x19. **LIVE-VERIFIED** (probe
  inside the CSS): L = bit 0x40 appears in both words on L tap.
  CAUTION: external (out-of-process) polling of this array reads ZEROS even
  while buttons are held — on the Slippi build inputs flow through a ring
  buffer (~0x80440A4C, ptrs at 0x804C5F30) and the HSD copy is only valid
  during the scene-processing window. Verify input facts from INSIDE hooks.
- The two pad-read blocks: 0x80260330- (door_count==1 CSS) and 0x80260440-
  (multi-door CSS; r19=held from +0, r28=pressed from +8, port = lbz 4(r31)).

## Cursor vs coin arrays (LIVE-VERIFIED, corrects the plan's assumption)
- `0x804A0BC0 + port*4` → **hand/cursor** data: port u8 +0x4, state u8 +0x5,
  hand position f32 X +0xC, Y +0x10. Tracks the hand ALWAYS (coin held or not).
- `0x804A0BD0 + port*4` → **coin** data: position f32 X +0x8, Y +0xC. Tracks
  the hand while the coin is held; freezes on the tile when placed.
- Toggle hook hit-tests the HAND (+0xC/+0x10) → works in every coin state.
  The game's side-drop check hit-tests the COIN (you drop the coin).

## Static data (verified by dump)
| what | address | notes |
|---|---|---|
| icons[26] | `0x803F0B24` = 0x803F0A48+0xDC | stride 0x1C: char_kind +1, state +2 (0/1/2), jobj_vs +4, sfx +8 (s32), bounds f32 l/r/u/d +0xC/+0x10/+0x14/+0x18 |
| icons[25] | `0x803F0DE0` | zero-fill (state 0, bounds 0) — the Phase-2 tile slot |
| doors[4] | `0x803F0DFC` = 0x803F0A48+0x3B4 | stride 0x24: p_kind +0xB (0 HMN/1 CPU/3 closed), costume +0xD, sel_icon +0xE |
| coin data ptrs | `0x804A0BD0` (= 0x804A0BC0+0x10), 4 ptrs | X +0x8, Y +0xC (f32) |
| CSSData ptr | `0x804D6CB0` (r13−0x49F0) | players c_kind @ +0x70 + p*0x24 |
| door count | `0x804D6CF5` (r13−0x49AB) | 1 on 1P-style CSS → gate filtering off |
| 1P remap | `0x804D6CF0/F1` (r13−0x49B0/−0x49AF) | |

## CSS grid geometry (from icons bounds dump)
- Row 1 (y 13..20): 9 tiles, x −30 → 30.2 (DrM, Mario, Luigi, Bowser, Peach, Yoshi, DK, Falcon, Ganon)
- Row 2 (y 6..13): 9 tiles (Falco, Fox, Ness, ICs, Kirby, Samus, Zelda, Link, YLink)
- Row 3 (y −1..6): 7 tiles, x −23.4 → 23.6 (Pichu, Pika, Puff, Mewtwo, GnW, Marth, Roy)
- **The side-drop strips (±24.4..30/30.2, y −1..6) are exactly tile-sized
  slots flanking row 3.** Phase-2 option B: convert the RIGHT strip into the
  '?' tile (hit zone already exists; patch its handler from instant-roll to
  mystery-select) instead of extending the icons array — likely much smaller
  patch surface. Decide at Phase 2 spike.

## Toggle hook site
`mnCharSel_802669F4_OnFrame` — inject at `0x80266A0C` (first instruction after
r31 = 0x804A0BC0 is set; replaced insn `lwz r3, -0x49B4(r13)`). Runs once per
CSS frame, never in other scenes. r0, r3–r12 usable (re-execute replaced insn).

## Misc
- HSD_Randi = `0x80380580` (arg r3 = exclusive max, returns r3).
- SFX: `lbAudioAx_800237A8(id, 0x7F, 0x40)`; side-drop random plays id 0xB8.
  Menu blip: `lbAudioAx_80024030(2)`.
- c_kind sentinel 0x21 = "no pick"; sel_icon ≥ 0x19 = "nothing selected".
- Ready-to-start checks (Phase 2): decomp lines ~3475/3487 → candidates among
  the cmplwi-0x19 sites at 0x80261F8C/0x802620CC/0x802621E0 (disambiguate at
  Phase 2).
- DOL map: text1 covers 0x80005940+0x3B1900; data5 0x803B9840+0x77E80 (icons,
  doors); data7 0x804D79E0+0x7220 (rtoc floats).
- Slippi-build coexistence (live-checked 2026-06-10): all our hook sites read
  identical to the ISO with Slippi's own codes (UCF etc.) active — no
  conflicts. OnFrame C2 @ 0x80266A0C runs per CSS frame on BOTH the VS CSS
  (door_count=4) and 1P CSS (door_count=1).
- Scratch RAM: 0x817F8000 held probe data fine across the CSS session; must
  still be diffed across a full match (Phase 1 test matrix) before final.
- Dev loop: dev Dolphin copy at build/dev-dolphin (portable; cheats enabled;
  keyboard pads: P1 arrows/X=A/Z=B/Q=L/W=R/Enter=Start, P2 uoyr/N=A/V=B/,=L).
  Launch: `Slippi Dolphin.exe --exec="<iso>"`. Codes: User/GameSettings/
  GALE01.ini [Gecko]+[Gecko_Enabled]. Boot lands in Slippi Online submenu:
  Z, Z, Down, A, A reaches the VS CSS (taps via hold_key ~0.08-0.15s; the
  first input after a click needs ~0.5s settle).
