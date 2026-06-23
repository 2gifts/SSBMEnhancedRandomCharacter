# Changelog

## v1.0.0

First release. Per‑port random‑character pools built live on the Melee VS
character select screen:

- **Per‑port pools** — tap **L** to add/remove the hovered character, tap **L**
  on your player card to clear. Empty pool = full‑roster random. Pools are per
  controller port and RAM‑resident.
- **Instant random** — drop your coin on the left random strip for a Melee‑style
  roll constrained to your pool, placed immediately.
- **Mystery random** — drop your coin on the right mystery zone for a hidden
  pick, revealed only when the match loads and re‑rolled fresh every game.
- **Online‑safe on Slippi** — every random resolves to a concrete character
  before it's transmitted, so netplay stays in sync and the opponent needs
  nothing installed. Verified on a Direct connection.
- **Universal** — runs on stock Melee NTSC 1.02 and on m‑ex builds (e.g.
  Akaneia); the roster size and tables are read live.
- Runs on Slippi Dolphin, regular Dolphin, and Wii console (Nintendont `.gct`
  or a pre‑patched ISO).

### Fixes during development

- **Online mystery crash (invalid read).** Locking in a hidden mystery online
  could crash at match start with an invalid read. With the card held blank, the
  game derived its internal "no‑selection" value into the transmit slot — an
  out‑of‑range character id that the match setup then indexed on. The fix stores
  the rolled pick and re‑asserts it into the slot late each frame, after the
  game's derivation, so a valid character is always what gets transmitted and
  loaded.
