# Enhanced Random Character for Melee

![Melee NTSC 1.02](https://img.shields.io/badge/Melee-NTSC%201.02-e4002b)
![Platforms](https://img.shields.io/badge/platform-Slippi%20%7C%20Dolphin%20%7C%20Wii-blue)
![Netplay](https://img.shields.io/badge/netplay-safe-1fc28e)
![License](https://img.shields.io/badge/license-MIT-green)

*A per‑port **random character** mod for **Super Smash Bros. Melee** — limit random
to your chosen characters (your mains, a practice subset), or take a hidden
**“mystery” blind pick** revealed only at match load. Online / netplay‑safe
**Gecko codes** for **Slippi** and **Dolphin**, plus **Wii** via **Nintendont**.*

A Super Smash Bros. Melee code mod that gives **each controller port its own
random‑character pool**, built live on the character select screen. Pick the
characters *you* feel like playing, then either roll one instantly or take a
**mystery pick that stays hidden until the match loads**. Every other player
keeps their own pool.

Works **offline** (vanilla VS) and **online on Slippi** — and online, *only you
need it installed*. It also runs on real **Wii hardware** (Nintendont) and on
**m‑ex builds** like the Akaneia Build (it detects which game is running).

**Great for:** restricting random to your mains or a practice pool · a
random‑secondary or random‑character challenge run · a blind / mystery pick that
surprises you at the loading screen · a fairer custom random than rolling the
whole roster.

## What it does

On the **VS‑mode character select screen**, with your token in hand or placed:

| Action | Effect |
|---|---|
| Hover a character, **tap L** | Add it to your pool (tap again to remove — a sound confirms each toggle) |
| **Tap L on your player card** | Clear your pool (reset sound) |
| **Drop your coin on the left random strip** | **Instant random** — a character from your pool is rolled and placed right away (Melee‑style). Pick it back up with **B** and drop again to re‑roll. |
| **Drop your coin on the right mystery zone** | **Mystery random** — the pick is **hidden** and revealed only when the match loads, re‑rolled fresh every game. Leave the coin parked and just mash **Start** to keep getting new surprise characters. |
| **Press B** (hand over the grid) | Reclaim a parked mystery coin / cancel the mystery (READY drops until you place it again) |

- **Empty pool = vanilla behavior** (random over the whole roster), so the mod
  is invisible until you build a pool.
- Each port's pool is independent — four players, four pools.
- Pools live in RAM: they persist across matches and CSS visits, and reset when
  the console (or emulator) is powered off.

**Where the mystery zone is** — it sits at the height of the bottom character row:

- **Vanilla Melee:** the empty strip just to the **right** of the bottom row
  (drop level with Roy).
- **Akaneia / m‑ex:** the dead corner to the right of the bottom row, past Sonic.

The left random strip is Melee's normal random drop zone; the mod just
constrains the roll to your pool.

## Compatibility

| | |
|---|---|
| **Game** | Melee **NTSC 1.02** (`GALE01`), and m‑ex builds on the same ID (e.g. Akaneia) — auto‑detected |
| **Slippi Dolphin** | Offline VS **and** online (Direct tested; Unranked / Teams use the same CSS code path) |
| **Regular Dolphin** | Offline, any 1.02 ISO |
| **Wii console** | Nintendont — `.gct` codes, or a pre‑patched ISO |

**Online is desync‑safe, and your opponent needs nothing.** Slippi sends your
character to the opponent by reading your selection at the moment Start is
pressed. Every random — instant or mystery — resolves to a *concrete* character
that is already sitting in that slot before it's transmitted, so your opponent
just receives an ordinary character pick. There's nothing for them to install,
and no shared random state to desync. (The mystery pick is hidden from **you**
on your own screen until the match loads — that's the surprise.) Slippi's CSS
random number generator is never used for a shared decision, which is what makes
this safe; see [docs/DESIGN.md](docs/DESIGN.md) for the full argument.

> Ranked matchmaking enforces a stock game and is not a target for this mod.

## Install

The mod is a small set of Gecko codes — **no game files are modified.** Grab the
files from [`dist/`](dist/).

### Slippi Dolphin (most common)

1. Copy [`dist/GALE01r2.ini`](dist/GALE01r2.ini) to your Slippi user folder:

   ```
   %APPDATA%\Slippi Launcher\netplay\User\GameSettings\GALE01r2.ini
   ```

   (On Windows, paste `%APPDATA%\Slippi Launcher\netplay\User\GameSettings` into
   the Explorer address bar to open it. Back up any existing `GALE01r2.ini`
   first.)
2. Turn on cheats: **Slippi Dolphin → Config → General → ☑ Enable Cheats**
   (or add `EnableCheats = True` under `[Core]` in
   `…\netplay\User\Config\Dolphin.ini`).
3. Launch Melee and go to **VS Mode**. Hover a character and tap **L** — you
   should hear the confirm sound.

**Or run the installer** (Windows): double‑click [`install.bat`](install.bat),
or `install.bat` from a terminal. It finds your Slippi folder, backs up any
existing file, copies the code in, and switches cheats on. Pass a path to target
a different Dolphin (`install.bat "D:\Dolphin\User"`).

### Regular Dolphin (offline)

Copy [`dist/GALE01.ini`](dist/GALE01.ini) to your Dolphin user folder's
`GameSettings\` (e.g. `Documents\Dolphin Emulator\GameSettings\GALE01.ini`),
then enable cheats (**Config → General → ☑ Enable Cheats**) and load your 1.02
ISO. Or right‑click the game → **Properties → Gecko Codes** and confirm the
`RandomPool …` codes are listed and ticked.

### Wii console (Nintendont)

**Simple route — `.gct` codes:**

1. Copy [`dist/GALE01.gct`](dist/GALE01.gct) to `sd:\codes\GALE01.gct` on your
   Nintendont SD/USB.
2. In Nintendont's settings, turn **Cheats** on. Boot your normal NTSC 1.02 (or
   Akaneia) ISO.

> ⚠️ Do **not** use the `.gct` together with **Slippi Nintendont** — Slippi
> injects its own codes into the same region and the two overflow it, which
> crashes the game when you open the Rules or Name‑Entry menus. For Slippi
> Nintendont, use the patched‑ISO route below instead.

**Patched‑ISO route (Slippi Nintendont, or to avoid the cheat region entirely):**

```
python tools/dolpatch.py <your-clean-1.02.iso> <output.iso>
```

This bakes the codes directly into a copy of the ISO (it uses free DOL space and
doesn't touch any Slippi hook, so Slippi recording keeps working). Put the output
ISO on your SD/USB and make sure Cheats is **off** / there's no `GALE01.gct` in
`/codes/`.

## Uninstall

Delete the file you added (`GALE01r2.ini`, `GALE01.ini`, or `sd:\codes\GALE01.gct`)
and restore your backup if you made one. The installer keeps a `.erc-backup`
copy you can restore. For a patched ISO, just go back to your original ISO.

## FAQ

**Does my opponent need the mod online?**
No. Your random becomes a real character before Slippi transmits it, so your
opponent receives a perfectly normal pick — nothing to install on their end, and
no desync.

**Will it desync netplay?**
No. The only thing that crosses the wire is your concrete character selection,
exactly as in stock Slippi. The unsynced CSS random number generator is never
used for anything both clients have to agree on. See
[docs/DESIGN.md](docs/DESIGN.md).

**Is the mystery pick hidden from my opponent too?**
The design goal is hiding it from **you** — on your own screen the card stays
blank until the match loads. Online, your selection is still transmitted (that's
what keeps netplay in sync), so treat the surprise as being for the player using
the mod.

**Does it work on the Akaneia Build / other m‑ex roster mods?**
Yes — the code reads the live roster size and tables, so a 25‑character vanilla
roster and a larger m‑ex roster both work. The mystery zone moves to the dead
corner past the last row on those builds.

**An empty pool does nothing?**
Correct — with no characters added, random rolls the full roster, identical to
vanilla. The mod only changes behavior once you've built a pool.

**Does it touch my game file / save?**
No. It's Gecko codes loaded by the emulator (or baked into a *copy* of the ISO
for console). Your ISO and saves are untouched.

## How it works

Ten small PowerPC hooks, injected as Gecko codes, all on the character select
screen:

- **list editing** — reads each port's L button and toggles the hovered
  character in/out of that port's pool, with sound feedback and a clear gesture;
- **instant roll** — replaces Melee's random roll with one constrained to your
  pool (one hook covers the side‑drop and the controller‑unplug fallbacks);
- **the mystery** — arms a parked coin in the game's "no pick" state so the card
  reads blank, rolls a concrete pick from your pool and holds it in the
  transmit slot, keeps the slot looking empty (selection box, portrait render,
  and the online "ready to connect" gate are all re‑asserted where the game
  tries to undo them), and re‑rolls fresh each match.

The source, [`src/build_codes.py`](src/build_codes.py), is a small Python
assembler that emits the codeset and is heavily commented; the netplay‑safety
argument and the reverse‑engineering notes are in
[docs/DESIGN.md](docs/DESIGN.md) and [docs/addresses.md](docs/addresses.md). The
`tools/` folder holds the Python tooling used to build, patch a console ISO, and
verify the mod against a live Dolphin — none of it is needed to install or play.

Rebuild the codes from source with:

```
python src/build_codes.py
```

## Credits

- Built on the reverse‑engineering work of the Melee community — the
  [doldecomp/melee](https://github.com/doldecomp/melee) decompilation, the
  Slippi team, and the many authors of custom‑random and CSS codes that mapped
  this territory first.
- A Melee companion to the Project+
  [Per‑Port Random Subset](https://github.com/2gifts/ProjectPlusRandomFilterMod).

## License

MIT — see [LICENSE](LICENSE). Super Smash Bros. Melee is the property of Nintendo
/ HAL Laboratory; this repository contains only original code and documentation.

---

<sub>**Also known as / keywords:** Melee random character mod · SSBM random character
select screen · Slippi random character · custom random / random filter · random
character generator and picker · mystery / blind pick · per‑port random ·
20XX‑style random · Melee Gecko code · Dolphin / Nintendont · Akaneia / m‑ex.</sub>
