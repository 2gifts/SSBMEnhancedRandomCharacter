# Per-Port Random — design & netplay-safety

Melee NTSC 1.02 (`GALE01`). One Gecko codeset, three player-facing features,
built to be **online-safe on Slippi netplay** and to read cleanly.

## Features

- **Per-port random pool.** Tap **L** on a character to add/remove it from
  *your* port's pool. Empty pool = full roster. Tap **L** on your player card
  to clear the pool. Pools are per controller port, RAM-resident.
- **Instant random** ("melee style"). Drop your coin on the game's native
  random side-zone → a concrete random character from your pool, shown
  immediately. This is just Melee's own random drop with the roll constrained
  to your pool — no new selection state.
- **Mystery random** ("true random"). Drop your coin on the mystery zone → the
  pick is hidden on the CSS and revealed only when the match loads, re-rolled
  fresh every game.

## The netplay-safety model (why this is desync-proof)

Slippi transmits a player's selection to the opponent by reading the CSS
player block — character at `+0x70`, costume at `+0x73` (stride `0x24`) — **at
the instant Start is pressed** (`FN_TX_LOCK_IN`, gated on the Start button).
The opponent's view is built purely from that packet. Two consequences drive
the whole design:

1. **A random must resolve to a concrete character that is sitting in `+0x70`
   before the Start-press read.** The CSS RNG is *not* synchronized between
   clients, so only the local client may roll; the concrete result transmits
   normally and both clients agree. Resolving *after* transmit (e.g. at match
   load) would desync.
2. **Only the local client rolls its own port.** The opponent receives a
   concrete character, never re-rolls it. So an unsynced `HSD_Randi` is
   irrelevant — it never feeds a shared decision.

Both features satisfy (1) by construction:

- *Instant random* is a native pick: the game writes a concrete `+0x70` at drop
  time and transmits it like any character. Nothing to get wrong.
- *Mystery* keeps the door in the native "no pick" sentinel state on the CSS
  (so the character is genuinely hidden — no portrait, name, or token is ever
  rendered) and resolves to a concrete `+0x70` **in the CSS OnFrame hook, on
  the Start-press edge.** OnFrame runs at the top of the scene's per-frame
  update, *before* the input/transmit logic of that same frame, so the
  concrete value is in place when Slippi reads `+0x70` to transmit. Offline,
  the same write lands before the match-setup reads it. One resolution point,
  correct in both environments.

`HSD_Randi` is never used to make a decision both clients must agree on — it
only picks the *local* port's concrete character, which then transmits. No
shared CSS randomness exists anywhere in the codeset.

## Hooks (8)

| hook | site | one job |
|---|---|---|
| `roll_filter` | `0x8025FB74` (replaces `bl HSD_Randi`) | constrain any roster roll to the local port's pool |
| `css_frame`   | `0x80266A0C` (CSS OnFrame) | param cache · per port: hide an armed coin, resolve on the Start edge · L toggle/clear |
| `css_enter`   | `0x8026688C` (CSS OnEnter) | re-hide armed ports on CSS (re-)entry — this is the per-match re-roll |
| `arm_gate`    | `0x802609F4` (A-press strip test) | coin dropped in the mystery zone → arm + park the coin |
| `ready`       | `0x8026304C` (ready scan) | an armed door counts as "ready to fight" |
| `cursor_ok`   | `0x80263108` (ready cursor pass) | an armed door's parked cursor doesn't block ready |
| `no_summon`   | `0x802621DC` (hover-summon sel load) | don't yank an armed door's parked coin back to the hand |
| `pickup`      | `0x802620C8` (B-pickup sel load) | B reclaims the parked coin and cancels the mystery |

The mystery lifecycle is owned entirely by `c_kind`'s state: **sentinel while
on the CSS** (hidden — the card display follows `sel_icon`, which stays the
sentinel, so no portrait/name/token ever renders), **concrete on a Start
press** (`gs`, any human's Start — the lock-in moment, caught in OnFrame
before Slippi transmits), **re-hidden on CSS re-entry** (`css_enter`). No
timestamps, no frame windows — the scene state itself is the source of truth.

`ready` / `cursor_ok` / `no_summon` are the small price of hiding the pick by
parking the coin off-grid: the door sits in the native "no pick" sentinel
state (which is what keeps it invisible), so those three make that sentinel
state read as a ready, placed, non-summoning pick. This is deliberately a
visual-only deception layered on native selection state — it never fights the
ready/transmit machinery that Slippi hooks for netplay.

**CPUs** (offline only): the same flow works. A player can carry a CPU's coin
to the mystery zone; the CPU resolves from *its own* port's pool on the Start
press, exactly like a human port. Online there are no CPUs, so this path is
inert there.

**Premature Start** (offline, no ready opponent): the pick resolves early but
harmlessly — it stays invisible (card follows `sel_icon`) and is re-resolved
on the real match-start Start. Online a Start press *is* the lock-in, so
resolving then is the intended behaviour.

## Universal build support (vanilla + m-ex / Akaneia)

The roster differs on m-ex builds (32 chars, relocated tables). `css_frame`
detects the build once per frame from the instruction at `0x8025FB70`
(`li r3,0x19` ⇒ vanilla) and caches roster count, icon-table base, and the
"no selection" / "no pick" sentinels. Every other hook reads the cache, so the
same codeset runs on both. `roll_filter` is build-agnostic: the game hands it
the live count (`r3`) and table base (`r30`).

## Scratch RAM `0x817F8100` (`RLV3`)

```
+0x00 magic 'RLV3'        +0x08 count   +0x0C icons    +0x10 sel-none
+0x04 pending SFX         +0x14 ck-none +0x18 is_van   +0x1C roll-count spill
+0x20 scratch / spills (0x20..0x2B) · +0x2C prev sub-screen-pending · +0x2D gs
+0x30 armed flag[port]    (4 bytes)
+0x40 + port*0x30: u8 count, u8 enabled[47]    (per-port pool, icon-index space)
```

## What was and wasn't tested

Validated on Slippi Dolphin against the **offline VS** CSS — the same
`mnCharSel` code the online CSS runs — on stock Melee and the Akaneia m-ex
build: a 19-check battery (pool build/clear, per-port isolation, instant
rolls, mystery arm/roam/ready/pickup/re-arm, sub-screen round-trip, start
roll, persistence, per-match re-roll) and an 11-check CPU-carry suite, all
passing on both builds. The 8 hook sites were confirmed not to overlap any
injection in Slippi's netplay codeset, and the mod was run with Slippi's CSS
codeset loaded alongside it with no conflict.

Online **determinism** is established by construction (concrete pick written
before the Start-press transmit; no shared CSS RNG). It has since also been
exercised over a real **two-client Direct connection**, which surfaced one
match-start crash that the construction argument had missed: with the mystery
card held blank, the game derived its internal *no-selection* value into the
transmit slot (`c_kind`) — an out-of-range character id the match-setup then
indexed on (invalid read). The fix rolls a concrete pick into a scratch slot
and re-asserts it into `c_kind` late each frame, after the game's derivation,
so a valid character is always what gets transmitted and loaded. With that in
place the Direct connection loads cleanly. Unranked/Teams run the same CSS
code path; Ranked enforces a stock game and is not a target.
