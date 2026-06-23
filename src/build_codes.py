"""Per-Port Random — Gecko codeset for SSB Melee NTSC 1.02 (GALE01).

Universal: runs on stock Melee and on m-ex builds (e.g. Akaneia, 32 chars).
Online-safe on Slippi netplay. See docs/DESIGN.md for the netplay-safety
argument; the short version:

  * Slippi transmits a port's character (CSSData player +0x70 = c_kind) to
    the opponent at lock-in. A random must therefore resolve to a CONCRETE
    c_kind *before* that read, and only the local client may roll (the CSS
    RNG is not synced). Both features satisfy this:
      - instant random is a native pick (concrete at drop time);
      - mystery holds a concrete c_kind the whole time -- it is never shown,
        only transmitted (offline it resolves on the Start edge instead,
        before that frame's match-start, which is the offline lock-in).

Online hidden mystery (the card must look EMPTY while c_kind holds the real
pick): an armed door is parked in the game's native no-pick state -- coin
hidden, sel_icon at the sentinel -- so the game draws a blank card. The game
keeps trying to undo this, so we re-assert the sentinel wherever it touches:
  * the portrait -- DB34 (the door-display refresh) draws the card from
    sel_icon, so db_blank forces sel_icon to the sentinel at DB34's entry;
    every render (on commit, on connect-code/rules sub-screen close, on CSS
    re-entry) then draws blank at the source, no per-frame chasing, no flash.
  * the connect gate -- the game recomputes "ready" to false each frame for a
    blank slot, so gate_force forces the ready byte back (Start works) and
    re-asserts sel_icon + the hidden coin late in the frame as a backstop.
  * the pick -- css_frame rolls a concrete c_kind once per match (css_enter
    resets it on each entry, so it re-rolls); it only feeds the transmit.

Build detection: the instruction at 0x8025FB70 is `li r3,0x19` on stock
Melee and a data load on m-ex. css_frame caches roster count, icon-table
base, and the no-selection / no-pick sentinels once per frame; every other
hook reads the cache. roll_filter is build-agnostic (the game hands it the
live count in r3 and table base in r30).

Scratch @ 0x804D6AA0 (magic 'RLV3'):
  +0x00 magic        +0x08 count   +0x0C icons   +0x10 sel-none
  +0x04 pending SFX  +0x14 ck-none +0x18 is_van  +0x1C roll-count spill
  +0x20..0x2F  scratch / call spills
  +0x30 + port  armed flag (4 bytes)
  +0x34 + port  rolled mystery pick / c_kind (4 bytes)
  +0x40 + port*0x30  per-port pool: u8 count, u8 enabled[47] (icon index)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from geckogen import *  # noqa: F401,F403

# ---- addresses ----
# Scratch base. MUST be a low, genuinely-unused region: 0x804D6AA0 sits in
# the game's scratchpad family inside a confirmed-free 603-byte zero run
# (0x804D694D..0x804D6BA8) anchored on 0x804D6B90 (documented free by 20XX),
# and inside Slippi's rollback savestate range so it's netplay-consistent.
# (The old 0x817F8100 was in the OS-reserved FST/ArenaHi tail at the top of
# MEM1 — fine offline, but reclaimed on the transition into online play,
# which caused an invalid-read crash entering Direct mode.)
SC_HI, SC_LO = 0x804D, 0x6AA0                # scratch base 0x804D6AA0
MAGIC_HI, MAGIC_LO = 0x524C, 0x5633          # 'RLV3'
PAD_HI, PAD_LO = 0x804C, 0x20BC              # HSD_PadCopyStatus, stride 0x44
DOORS_HI, DOORS_LO = 0x803F, 0x0DFC          # doors[4], stride 0x24
HAND_HI, HAND_LO = 0x804A, 0x0BC0            # hand[port] @ +port*4
COIN_HI, COIN_LO = 0x804A, 0x0BD0            # coin[port] @ +port*4
RANDI_HI, RANDI_LO = 0x8038, 0x0580          # HSD_Randi(maxExclusive)->r3
SFX_HI, SFX_LO = 0x8002, 0x37A8              # lbAudioAx_800237A8(id,0x7F,0x40)

# ---- scratch offsets ----
SFX = 0x04
P_COUNT, P_ICONS, P_SELNONE, P_CKNONE, P_ISVAN, ROLLCNT = (
    0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C)
SCR, SPILL_PORT = 0x20, 0x28          # 0x24 also used as a transient spill
PREV_PEND, GSTART = 0x2C, 0x2D
FLAGS = 0x30                                  # armed flag, 1 byte per port
PEND_CK = 0x34                                # rolled mystery pick, 1 byte per port
LISTS, LIST_STRIDE, LIST_CAP = 0x40, 0x30, 0x2F

START_MASK = 0x1000                           # Start button (held/pressed word)
L_MASK = 0x40                                 # L button
HIDDEN = 0x10                                 # JOBJ_HIDDEN flag bit


# ---- ops not in geckogen ----
def stwx(rs, ra, rb): return 0x7C00012E | (rs << 21) | (ra << 16) | (rb << 11)
def subf(rd, ra, rb): return 0x7C000050 | (rd << 21) | (ra << 16) | (rb << 11)
def bctr():           return 0x4E800420


def sc(reg):
    """Load the scratch base 0x804D6AA0 into reg."""
    return [lis(reg, SC_HI), ori(reg, reg, SC_LO)]


def css_guard(bail):
    """Bail (to `bail`) unless the CSSData pointer is a valid MEM1 address.
    Guards our automatic hooks against dereferencing a null/garbage CSSData
    during scene transitions / unexpected contexts. (Deliberately does NOT
    check door count: at OnEnter that isn't initialised yet.) Uses r8,r9,r10."""
    return [
        lwz(9, -0x49F0, 13),                        # CSSData ptr
        rlwinm(8, 9, 0, 0, 6), lis(10, 0x8000),
        cmplw(8, 10), bne(bail),                    # not 0x80/0x81xxxxxx
    ]


def call(hi, lo):
    """Call an absolute function address via CTR (clobbers r12, LR)."""
    return [lis(12, hi), ori(12, 12, lo), mtctr(12), bctrl()]


def show_coin(port_reg, flag_reg, pfx):
    """Set JOBJ_HIDDEN on port's coin model when armed (flag != 0), clear it
    otherwise. Walks coin[port] -> gobj -> jobj(+0x28). Each link is checked
    for a valid MEM1 pointer (not just non-null) before it is followed, so a
    garbage pointer during a scene transition is a no-op, not an invalid read.
    Uses r8,r10,r12. Labels prefixed by `pfx`."""
    def valid():                               # bail to done unless r8 is 0x80/0x81xxxxxx
        return [rlwinm(10, 8, 0, 0, 6), lis(12, 0x8000),
                cmplw(10, 12), bne(pfx + 'done')]
    return [
        lis(8, COIN_HI), ori(8, 8, COIN_LO),
        rlwinm(12, port_reg, 2, 0, 29), lwzx(8, 8, 12),
        *valid(),
        lwz(8, 0, 8), *valid(),                # gobj
        lwz(8, 0x28, 8), *valid(),             # jobj
        lwz(12, 4, 8),
        cmplwi(flag_reg, 0), beq(pfx + 'unhide'),
        ori(12, 12, HIDDEN), b(pfx + 'set'),
        label(pfx + 'unhide'), rlwinm(12, 12, 0, 28, 26),   # clear JOBJ_HIDDEN
        label(pfx + 'set'), stw(12, 4, 8),
        label(pfx + 'done'),
    ]


def pool_walk(pfx):
    """Walk a port's enabled[] list to the k-th enabled icon.
    In: r10 = enabled[] base, r11 = scratch, r3 = k. Out: r5 = icon index.
    Clobbers r5,r6,r7 (and consumes r3). Labels prefixed by `pfx`."""
    def L(name):
        return pfx + name
    return [
        lwz(7, P_COUNT, 11),
        cmplwi(7, LIST_CAP), ble(L('cap')), addi(7, 0, LIST_CAP),
        label(L('cap')),
        addi(5, 0, 0),
        label(L('walk')),
        lbzx(6, 10, 5), cmplwi(6, 0), beq(L('wnext')),  # not enabled -> next
        cmpwi(3, 0), beq(L('have')),                    # k-th enabled -> found
        addi(3, 3, -1),
        label(L('wnext')),
        addi(5, 5, 1), cmpw(5, 7), blt(L('walk')),
        addi(5, 0, 0),                                  # ran off the end -> idx 0
        label(L('have')),
    ]


def roll_pool(pfx):
    """Roll a concrete char_kind from the current port's pool into the
    door's player block. Inputs: r11 = scratch base, r4 = port. Uses
    r3,r5,r6,r7,r9,r10,r12; preserves nothing across the HSD_Randi calls
    except via SPILL_PORT. Labels are prefixed by `pfx` for uniqueness."""
    def L(name):
        return pfx + name
    return [
        stw(4, SPILL_PORT, 11),
        # pool[port]: count at +0, enabled[] at +1
        mulli(10, 4, LIST_STRIDE), addi(10, 10, LISTS), add(10, 11, 10),
        lbz(9, 0, 10),
        cmplwi(9, 0), beq(L('full')),          # empty pool -> full roster
        mr(3, 9), *call(RANDI_HI, RANDI_LO),   # r3 = k in [0,count)
        *sc(11), lwz(4, SPILL_PORT, 11),
        mulli(10, 4, LIST_STRIDE), addi(10, 10, LISTS + 1), add(10, 11, 10),
        *pool_walk(L('w')),                    # r5 = icon idx of the k-th enabled
        lwz(6, P_ICONS, 11), mulli(7, 5, 0x1C), add(7, 7, 6),
        lbz(12, 2, 7), cmplwi(12, 0), bne(L('write')),  # in-list pick visible?
        label(L('full')),                      # roll the full roster instead
        *sc(11), lwz(3, P_COUNT, 11), *call(RANDI_HI, RANDI_LO),
        mr(5, 3), *sc(11),
        lwz(6, P_ICONS, 11), mulli(7, 5, 0x1C), add(7, 7, 6),
        lbz(12, 2, 7), cmplwi(12, 0), beq(L('full')),   # retry locked icon
        label(L('write')),
        lbz(9, 1, 7),                          # icons[idx].char_kind
        lwz(4, SPILL_PORT, 11),
        lwz(6, -0x49F0, 13), mulli(10, 4, 0x24), add(6, 6, 10),
        stb(9, 0x70, 6),                       # player[port].c_kind = concrete
        addi(10, 11, PEND_CK), stbx(9, 10, 4),  # remember pick (gate_force re-asserts it online)
        lis(6, DOORS_HI), ori(6, 6, DOORS_LO), add(6, 6, 10),
        addi(12, 0, 0), stb(12, 0xD, 6),       # costume 0
    ]


# ======================================================================
# roll_filter @ 0x8025FB74  (replaces `bl HSD_Randi` in the roll core)
# ----------------------------------------------------------------------
# Constrain any roster roll to the local port's pool. The game has already
# put the roster count in r3 and the icon-table base in r30 (both builds),
# and the door in r27. Returns the chosen icon index in r3. Falls back to a
# plain HSD_Randi(count) for: 1-player CSS, empty pool, or a locked pick.
# ======================================================================
def roll_filter():
    return asm([
        *sc(11), stw(3, ROLLCNT, 11),          # save live roster count
        # A single open door normally means a 1P-style CSS, where the port
        # remap is ambiguous, so we bail to a vanilla roll. The online CSS is
        # the exception: before the opponent connects it sits at one open
        # door too, yet door 0 -> port 0 maps reliably (scene major 8), so we
        # let filtering through there.
        lbz(12, -0x49AB, 13), cmplwi(12, 1), bne('port_chk'),  # >1 door: VS
        lis(9, 0x8047), ori(9, 9, 0x9D30), lbz(9, 0, 9),       # scene major
        cmplwi(9, 8), bne('vanilla'),                          # 1 door, offline 1P
        label('port_chk'),
        clrlwi(12, 27, 24), cmplwi(12, 3), bgt('vanilla'),    # port = door
        lwz(10, 0, 11), lis(9, MAGIC_HI), ori(9, 9, MAGIC_LO),
        cmpw(10, 9), bne('vanilla'),           # storage uninitialised
        mulli(10, 12, LIST_STRIDE), addi(10, 10, LISTS), add(11, 11, 10),
        lbz(9, 0, 11), cmplwi(9, 0), beq('vanilla'),          # empty pool
        mr(3, 9), *call(RANDI_HI, RANDI_LO),   # r3 = k in [0,count)
        *sc(11), clrlwi(12, 27, 24),
        mulli(10, 12, LIST_STRIDE), addi(10, 10, LISTS + 1), add(10, 11, 10),
        *pool_walk('rf_'),                     # r5 = icon idx of the k-th enabled
        mulli(6, 5, 0x1C), add(6, 6, 30), lbz(6, 0xDE, 6),    # icons[idx].state
        cmplwi(6, 0), beq('vanilla'),          # locked -> fall back
        mr(3, 5), b('done'),
        label('vanilla'),
        *sc(11), lwz(3, ROLLCNT, 11), *call(RANDI_HI, RANDI_LO),
        label('done'),
    ])


# ======================================================================
# css_frame @ 0x80266A0C  (CSS OnFrame; orig `lwz r3,-0x49B4(r13)`)
# ----------------------------------------------------------------------
# Runs at the top of the per-frame CSS update, before input/transmit. Per
# port: maintain the mystery (hide the coin; resolve concrete on the Start
# edge), then handle an L press (toggle a tile, or clear over the card /
# side zones). A separate OnEnter hook re-hides on CSS re-entry, so the
# lifecycle here needs no timers.
# ======================================================================
def css_frame():
    return asm([
        # ---- one-time storage init ----
        *sc(11), lwz(12, 0, 11),
        lis(10, MAGIC_HI), ori(10, 10, MAGIC_LO),
        cmpw(12, 10), beq('inited'),
        stw(10, 0, 11),
        addi(9, 0, 0x100), addi(8, 0, 0),
        label('zloop'), addi(9, 9, -4), stwx(8, 11, 9), cmpwi(9, 4), bne('zloop'),
        label('inited'),

        # ---- cache build params ----
        lis(12, 0x8025), ori(12, 12, 0xFB70), lwz(12, 0, 12),
        lis(10, 0x3860), ori(10, 10, 0x0019), cmpw(12, 10), bne('mex'),
        addi(8, 0, 0x19), stw(8, P_COUNT, 11), stw(8, P_SELNONE, 11),
        lis(8, 0x803F), ori(8, 8, 0x0B24), stw(8, P_ICONS, 11),
        addi(8, 0, 0x21), stw(8, P_CKNONE, 11),
        addi(8, 0, 1), stw(8, P_ISVAN, 11),
        b('params_done'),
        label('mex'),
        lwz(8, 0x150, 2), stw(8, P_COUNT, 11), stw(8, P_SELNONE, 11),
        lwz(8, 0, 2), addi(8, 8, 0xDC), stw(8, P_ICONS, 11),
        lwz(8, 0x14C, 2), stw(8, P_CKNONE, 11),
        addi(8, 0, 0), stw(8, P_ISVAN, 11),
        label('params_done'),

        # snapshot the sub-screen-pending byte so hooks that run later this
        # frame (e.g. pickup) can tell a sub-screen was open at frame start
        lbz(9, -0x49AA, 13), stb(9, PREV_PEND, 11),

        # did some human press Start this frame? That is the lock-in moment:
        # every armed door resolves to a concrete pick now. It is one global
        # event (a player who armed a CPU's coin presses Start on their own
        # pad), and online the only human is port 0, so this is that port's
        # Start press -- caught here at the top of OnFrame, before Slippi
        # reads +0x70 to transmit. Pressing Start with no ready opponent
        # resolves early but harmlessly: the pick stays invisible (the card
        # follows sel_icon, still the sentinel) and is re-resolved on the
        # real match-start Start.
        addi(8, 0, 0),
        addi(12, 0, 0),
        label('gs_loop'),
        lis(9, PAD_HI), ori(9, 9, PAD_LO), mulli(10, 12, 0x44), add(9, 9, 10),
        lwz(9, 8, 9), andi_(9, 9, START_MASK), cmplwi(9, 0), beq('gs_next'),
        addi(8, 0, 1),
        label('gs_next'),
        addi(12, 12, 1), cmpwi(12, 4), blt('gs_loop'),
        label('gs_done'),
        stb(8, GSTART, 11),

        # bail out of all per-port work if this isn't a sane CSS scene
        *css_guard('done'),

        # ================= per-port pass (r4 = port) =================
        addi(4, 0, 0),
        label('ploop'),
        lbz(9, -0x49AA, 13), cmplwi(9, 0), bne('next'),   # sub-screen up: skip

        # ---- coin visibility tracks the armed flag ----
        *sc(11),
        addi(10, 11, FLAGS), lbzx(5, 10, 4),
        *show_coin(4, 5, 'cv_'),
        cmplwi(5, 0), beq('lpress'),
        # armed. Offline: resolve the concrete pick on the match-start frame
        # (any human Start) -- the card stays blank, the pick lands before the
        # match loads. Online (scene major 8): Direct's connect/transmit
        # happens several screens after the CSS Start, so resolve ONCE the
        # moment the slot is armed and hold it -- sel_icon stays the sentinel
        # (blank card) while c_kind carries the real pick Slippi transmits at
        # lock-in. css_enter resets c_kind to the sentinel each entry, so this
        # re-rolls a fresh pick per match.
        lis(9, 0x8047), ori(9, 9, 0x9D30), lbz(9, 0, 9),  # scene major
        cmplwi(9, 8), beq('o_armed'),
        # offline armed: resolve the concrete pick on the Start frame.
        lbz(9, GSTART, 11), cmplwi(9, 0), beq('lpress'),
        *roll_pool('rp_'),
        b('next'),

        # online armed: roll a concrete pool pick ONCE, the moment the slot is
        # the sentinel (css_enter resets it per entry, so the pick re-rolls each
        # match). roll_pool stashes that pick in PEND_CK. We do NOT try to hold
        # c_kind here: the game clobbers it to its no-selection value every frame
        # (see gate_force), so gate_force re-asserts the PEND_CK pick late, after
        # that clobber. The card stays blank -- sel_icon is held at the sentinel
        # by gate_force and the portrait is blanked at the DB34 render by
        # db_blank. c_kind is never displayed; it only feeds Slippi's transmit.
        # Key the one-shot roll off PEND_CK, not c_kind: the game (and gate_force)
        # rewrite c_kind every frame, but PEND_CK == cknone means "not yet rolled"
        # and is only cleared by our roll / set by css_enter + arm_gate per match.
        label('o_armed'),
        addi(10, 11, PEND_CK), lbzx(9, 10, 4),
        lwz(12, P_CKNONE, 11), cmplw(9, 12), bne('next'),  # already rolled: hold
        *roll_pool('rp_'),
        b('next'),

        # ---- L press: toggle a tile, or clear ----
        label('lpress'),
        *sc(11),
        lis(10, PAD_HI), ori(10, 10, PAD_LO),
        mulli(9, 4, 0x44), add(10, 10, 9),
        lwz(9, 8, 10), andi_(9, 9, L_MASK), beq('next'),
        lis(10, DOORS_HI), ori(10, 10, DOORS_LO),
        mulli(8, 4, 0x24), add(10, 10, 8),
        lbz(8, 0xB, 10), cmplwi(8, 3), beq('next'),       # closed door
        lis(10, HAND_HI), ori(10, 10, HAND_LO),
        rlwinm(9, 4, 2, 0, 29), lwzx(10, 10, 9),
        cmplwi(10, 0), beq('next'),
        # aim point = the coin when it is in the hand (the game's hover
        # preview hit-tests the coin; the hand trails it), else the hand
        lis(12, COIN_HI), ori(12, 12, COIN_LO), lwzx(12, 12, 9),
        cmplwi(12, 0), beq('use_hand'),
        lbz(8, 5, 12), cmplwi(8, 0), beq('use_hand'),
        lfs(1, 8, 12), lfs(2, 0xC, 12), b('aimed'),
        label('use_hand'),
        lfs(1, 0xC, 10), lfs(2, 0x10, 10),
        label('aimed'),

        # clear zone: hand y < -1 (over the cards; no build has tiles there);
        # vanilla also keeps the classic side strips; m-ex the left corner.
        lfs(0, -0x3534, 2), fcmpo(2, 0), blt('clear'),    # y < -1
        lwz(8, P_ISVAN, 11), cmplwi(8, 0), beq('mexclear'),
        lfs(0, -0x3538, 2), fcmpo(2, 0), bge('tiles'),    # y < 6
        lfs(0, -0x3530, 2), fcmpo(1, 0), ble('tiles'),    # x > -30 ..
        lfs(0, -0x352C, 2), fcmpo(1, 0), blt('clear'),    # .. < -24.4
        lfs(0, -0x3528, 2), fcmpo(1, 0), ble('tiles'),    # x > 24.4 ..
        lfs(0, -0x3524, 2), fcmpo(1, 0), bge('tiles'),    # .. < 30.2
        b('clear'),
        label('mexclear'),
        lis(8, 0x40C6), ori(8, 8, 0x6666), stw(8, SCR, 11), lfs(0, SCR, 11),
        fcmpo(2, 0), bge('tiles'),                        # y < 6.2
        lfs(0, -0x3530, 2), fcmpo(1, 0), bge('tiles'),    # x < -30
        label('clear'),
        mulli(9, 4, LIST_STRIDE), addi(9, 9, LISTS), add(9, 11, 9),
        addi(8, 0, 0),
        stw(8, 0x00, 9), stw(8, 0x04, 9), stw(8, 0x08, 9), stw(8, 0x0C, 9),
        stw(8, 0x10, 9), stw(8, 0x14, 9), stw(8, 0x18, 9), stw(8, 0x1C, 9),
        stw(8, 0x20, 9), stw(8, 0x24, 9), stw(8, 0x28, 9), stw(8, 0x2C, 9),
        addi(8, 0, 0xB8), stw(8, SFX, 11),                # random-zone SFX
        b('next'),

        # ---- icon hit-test against the live table ----
        label('tiles'),
        addi(5, 0, 0), lwz(6, P_ICONS, 11), lwz(7, P_COUNT, 11),
        cmplwi(7, LIST_CAP), ble('tcap'), addi(7, 0, LIST_CAP),
        label('tcap'),
        label('iloop'),
        cmpw(5, 7), bge('next'),
        lbz(8, 2, 6), cmplwi(8, 1), blt('inext'),         # visible icons only
        lfs(0, 0xC, 6), fcmpo(1, 0), ble('inext'),        # x > l
        lfs(0, 0x10, 6), fcmpo(1, 0), bge('inext'),       # x < r
        lfs(0, 0x14, 6), fcmpo(2, 0), bge('inext'),       # y < u
        lfs(0, 0x18, 6), fcmpo(2, 0), ble('inext'),       # y > d
        mulli(9, 4, LIST_STRIDE), addi(9, 9, LISTS + 1), add(9, 11, 9),
        lbzx(8, 9, 5), xori(8, 8, 1), stbx(8, 9, 5),      # flip enabled[idx]
        mulli(12, 4, LIST_STRIDE), addi(12, 12, LISTS), add(12, 11, 12),
        lbz(10, 0, 12),
        cmplwi(8, 0), beq('dec'),
        addi(10, 10, 1), b('cnt'),
        label('dec'), addi(10, 10, -1),
        label('cnt'), stb(10, 0, 12),
        cmplwi(8, 0), beq('sfx_rem'),
        addi(8, 0, 0x02), b('sfx_set'),
        label('sfx_rem'), addi(8, 0, 0x01),
        label('sfx_set'), stw(8, SFX, 11),
        b('next'),
        label('inext'),
        addi(6, 6, 0x1C), addi(5, 5, 1), b('iloop'),

        label('next'),
        addi(4, 4, 1), cmpwi(4, 4), blt('ploop'),

        # ---- play a pending SFX once ----
        *sc(11), lwz(3, SFX, 11), cmpwi(3, 0), beq('done'),
        addi(8, 0, 0), stw(8, SFX, 11),
        addi(4, 0, 0x7F), addi(5, 0, 0x40), *call(SFX_HI, SFX_LO),
        label('done'),
        raw(0x806DB64C),                                  # orig lwz r3,-0x49B4(r13)
    ])


# ======================================================================
# css_enter @ 0x8026688C  (CSS OnEnter; orig `mflr r0`)
# ----------------------------------------------------------------------
# On every CSS (re-)entry, re-hide armed ports: the game restores each
# door's last concrete pick on re-entry, so reset it to the sentinel. This
# is what re-rolls the mystery fresh each match.
# ======================================================================
def css_enter():
    return asm([
        *sc(11),
        stw(3, SCR, 11), stw(4, SCR + 4, 11),  # preserve caller args
        lwz(12, 0, 11), lis(10, MAGIC_HI), ori(10, 10, MAGIC_LO),
        cmpw(12, 10), bne('skip'),             # storage not ready yet
        *css_guard('skip'),                    # only on a sane CSS scene
        addi(4, 0, 0),
        label('eloop'),
        addi(10, 11, FLAGS), lbzx(9, 10, 4),
        cmplwi(9, 0), beq('enext'),
        lwz(8, -0x49F0, 13), mulli(12, 4, 0x24), add(8, 8, 12),
        lwz(9, P_CKNONE, 11), stb(9, 0x70, 8),            # c_kind = sentinel
        addi(8, 11, PEND_CK), stbx(9, 8, 4),              # PEND_CK = sentinel (re-roll)
        label('enext'),
        addi(4, 4, 1), cmpwi(4, 4), blt('eloop'),
        label('skip'),
        lwz(3, SCR, 11), lwz(4, SCR + 4, 11),  # restore
        raw(0x7C0802A6),                                  # orig mflr r0
    ])


# ======================================================================
# arm_gate @ 0x802609F4  (A-press strip test; orig `rlwinm. r21,r28,..`)
# ----------------------------------------------------------------------
# A coin dropped in the mystery zone arms the port and parks the coin in a
# clean "no pick" state. Vanilla zone = right strip (24.4..30.2); m-ex zone
# = the dead corner past the bottom row (30..33.5); shared y window -1..6.2.
# Everything else continues build-native (the left strip = instant random).
# Must preserve r19/r21/r26/r28/r31; cr0 is restored at exit.
# ======================================================================
def arm_gate():
    return asm([
        raw(0x579505EF),                       # orig rlwinm. r21,r28,0,23,23
        beq('out'),                            # A not pressed
        lbz(11, -0x49AA, 13), cmplwi(11, 0), bne('out'),  # sub-screen up
        *sc(11),
        lwz(12, P_ISVAN, 11), cmplwi(12, 0), beq('mexz'),
        lfs(3, -0x3528, 2), lfs(4, -0x3524, 2),           # 24.4 .. 30.2
        b('ztest'),
        label('mexz'),
        lis(8, 0x41F0), stw(8, SCR, 11), lfs(3, SCR, 11),     # 30.0
        lis(8, 0x4206), stw(8, SCR, 11), lfs(4, SCR, 11),     # 33.5
        label('ztest'),
        rlwinm(12, 19, 2, 0, 29),
        lis(10, COIN_HI), ori(10, 10, COIN_LO), lwzx(10, 10, 12),
        cmplwi(10, 0), beq('out'),
        lfs(1, 8, 10), lfs(2, 0xC, 10),        # coin x, y
        lfs(0, -0x3534, 2), fcmpo(2, 0), ble('out'),      # y > -1
        lis(8, 0x40C6), ori(8, 8, 0x6666), stw(8, SCR, 11), lfs(0, SCR, 11),
        fcmpo(2, 0), bge('out'),               # y < 6.2
        fcmpo(1, 3), ble('out'),               # x > lo
        fcmpo(1, 4), bge('out'),               # x < hi
        # A single open door means either a real 1P-style CSS (ambiguous port
        # remap) or the online CSS (one door until the opponent connects).
        # 1P bails; the online CSS (scene major 8) arms -- the card stays
        # blank (sel_icon sentinel) and gate_force makes Slippi's connect gate
        # accept it, so the mystery is hidden until the match loads.
        lis(10, 0x804D), lbz(12, 0x6CF5, 10), cmplwi(12, 1), bne('armok'),
        lis(10, 0x8047), ori(10, 10, 0x9D30), lbz(10, 0, 10),  # scene major
        cmplwi(10, 8), bne('out'),                            # 1 door, offline 1P
        label('armok'),
        # ---- arm + park the coin (no pick) ----
        addi(10, 11, FLAGS), addi(9, 0, 1), stbx(9, 10, 19),  # flag = 1
        rlwinm(12, 19, 2, 0, 29),
        addi(10, 26, 0x10), lwzx(10, 10, 12),
        addi(9, 0, 0), stb(9, 5, 10), stb(9, 5, 31),      # coin/cursor: not held
        mulli(12, 19, 0x24),
        lis(10, DOORS_HI), ori(10, 10, DOORS_LO), add(10, 10, 12),
        lwz(9, P_SELNONE, 11), stb(9, 0xE, 10),           # sel = none
        lwz(10, -0x49F0, 13), add(10, 10, 12),
        lwz(9, P_CKNONE, 11), stb(9, 0x70, 10),           # c_kind = none
        addi(10, 11, PEND_CK), stbx(9, 10, 19),           # PEND_CK = none (roll fresh)
        clrlwi(3, 19, 24), *call(0x8025, 0xDB34),         # refresh door display
        addi(3, 0, 0xB8), addi(4, 0, 0x7F), addi(5, 0, 0x40),
        *call(SFX_HI, SFX_LO),                            # random-zone SFX
        lis(12, 0x8026), ori(12, 12, 0x22A8), mtctr(12), bctr(),  # build-native epilogue
        label('out'),
        raw(0x579505EF),                       # re-run orig (restore cr0)
    ])


# ======================================================================
# ready @ 0x8026304C  (ready scan; orig `lbz r0,0xE(r3)`, r8 = doors base)
# An armed door's sentinel sel_icon counts as a real pick, so the screen
# reaches "ready to fight".
# ======================================================================
def ready():
    return asm([
        lbz(0, 0xE, 3),                        # orig
        *sc(11), lwz(12, P_SELNONE, 11), cmplw(0, 12), bne('done'),
        subf(12, 8, 3), rlwinm(12, 12, 30, 2, 31),        # door idx
        addi(11, 11, FLAGS), lbzx(12, 11, 12),
        cmplwi(12, 0), beq('done'),
        addi(0, 0, 0),                         # counts as picked
        label('done'),
    ])


# ======================================================================
# cursor_ok @ 0x80263108  (ready cursor pass; orig `cmplwi r0,1`)
# Cursor state 1 (holding) normally blocks ready. An armed door's parked
# cursor must not block it. On m-ex a placed cursor legitimately sits in
# state 1, so there state 1 only blocks while the coin is actually in hand.
# ======================================================================
def cursor_ok():
    return asm([
        cmplwi(0, 1), bne('done'),
        subf(12, 30, 4), rlwinm(12, 12, 30, 2, 31),       # door idx
        *sc(11), addi(10, 11, FLAGS), lbzx(10, 10, 12),
        cmplwi(10, 0), bne('pass'),            # armed: never blocks
        lwz(10, P_ISVAN, 11), cmplwi(10, 0), bne('block'),    # vanilla: blocks
        rlwinm(10, 12, 2, 0, 29),
        lis(11, COIN_HI), ori(11, 11, COIN_LO), lwzx(11, 11, 10),
        cmplwi(11, 0), beq('blk_test'),
        lbz(10, 5, 11), cmplwi(10, 0), bne('block'),      # coin in hand: blocks
        label('blk_test'),
        mulli(10, 12, 0x24),
        lis(11, DOORS_HI), ori(11, 11, DOORS_LO), add(11, 11, 10),
        lbz(10, 0xE, 11), *sc(11), lwz(11, P_SELNONE, 11),
        cmplw(10, 11), blt('pass'),            # has a real pick: don't block
        label('block'),
        cmplwi(0, 1), b('done'),               # EQ -> blocks
        label('pass'),
        cmplwi(0, 0xFF),                       # NE -> passes
        label('done'),
    ])


# ======================================================================
# gate_force @ 0x80263250  (orig `lbz r0,-0x49AE(r13)`)
# ----------------------------------------------------------------------
# Runs every frame after the game re-derives the selection and before the
# branch into Slippi's connect gate (b at 0x80263258). For each armed port on
# the online CSS (scene major 8), it forces the ready byte 0x804D6CF7 (=
# -0x49A9(r13)) to 1 so Slippi's "ready to connect" gate (HandleInputsOnCSS)
# accepts the blank slot. The game recomputes that byte to 0 every frame, so
# this must hold it each frame. It also re-asserts sel_icon = sentinel (card
# stays blank; db_blank owns the portrait render) and re-forces c_kind to the
# concrete pick: the game derives c_kind = its no-selection value (0x1a on
# stock) from the blank sel_icon, an invalid roster index that crashes the
# match-setup, so we overwrite it with the stored pick after that derivation.
# Offline is unaffected (scene-major-8 gated). Leaf hook; temps saved in the
# stack red zone. The orig load is done last so r0 is valid for the cmplwi.
# ======================================================================
def gate_force():
    return asm([
        stw(7, -4, 1), stw(8, -8, 1), stw(9, -12, 1),
        stw(10, -16, 1), stw(11, -20, 1), stw(12, -24, 1),
        lis(9, 0x8047), ori(9, 9, 0x9D30), lbz(9, 0, 9),       # scene major
        cmplwi(9, 8), bne('restore'),
        *css_guard('restore'),                 # bail mid-transition (CSSData not ready)
        *sc(11),
        addi(7, 0, 0),                         # port counter
        label('gf_loop'),
        addi(10, 11, FLAGS), lbzx(9, 10, 7),   # r9 = flag[port]
        cmplwi(9, 0), beq('gf_next'),
        addi(12, 0, 1), stb(12, -0x49A9, 13),  # ready byte = 1
        mulli(12, 7, 0x24),
        lis(10, DOORS_HI), ori(10, 10, DOORS_LO), add(10, 10, 12),
        lwz(8, P_SELNONE, 11), stb(8, 0xE, 10),  # sel_icon = sentinel (blank)
        # the game derives c_kind = its no-selection value (0x1a on stock) from
        # the blank sel_icon -- an invalid roster index that crashes the match
        # setup. Overwrite it here, late (after that derivation), with the
        # concrete pick css_frame stored in PEND_CK, so the transmit/match-setup
        # read a valid character. The card still draws blank from sel_icon.
        # PEND_CK == cknone means css_frame has not rolled this slot yet: leave
        # c_kind alone so the sentinel survives for css_frame to roll next frame.
        addi(8, 11, PEND_CK), lbzx(8, 8, 7),   # r8 = PEND_CK[port]
        lwz(10, P_CKNONE, 11), cmplw(8, 10), beq('gf_nock'),
        lwz(10, -0x49F0, 13), add(10, 10, 12),  # player block (cssdata + port*0x24)
        stb(8, 0x70, 10),                      # c_kind = concrete pick
        label('gf_nock'),
        *show_coin(7, 9, 'gf_'),               # re-hide the coin model
        label('gf_next'),
        addi(7, 7, 1), cmpwi(7, 4), blt('gf_loop'),
        label('restore'),
        lwz(12, -24, 1), lwz(11, -20, 1), lwz(10, -16, 1),
        lwz(9, -12, 1), lwz(8, -8, 1), lwz(7, -4, 1),
        lbz(0, -0x49AE, 13),                   # orig (last, so r0 stays valid)
    ])


# ======================================================================
# db_blank @ 0x8025DB34  (door-display refresh DB34 entry; orig `mflr r0`)
# ----------------------------------------------------------------------
# DB34 redraws a door's card portrait from that door's sel_icon (it blanks
# the card when sel_icon >= selnone). It is the single render path -- the
# game calls it on commit, on sub-screen (connect-code/rules) close, and on
# CSS re-entry. So for an armed online port we force its sel_icon to the
# sentinel right here, before DB34 reads it: every portrait render draws
# blank at the source, with no per-frame chasing and no flash. r3 = door
# index on entry; only r11/r12 are touched (DB34 sets up its own regs after).
# ======================================================================
def db_blank():
    return asm([
        raw(0x7C0802A6),                       # orig mflr r0
        lis(11, 0x8047), ori(11, 11, 0x9D30), lbz(11, 0, 11),  # scene major
        cmplwi(11, 8), bne('db_done'),         # online CSS only
        clrlwi(11, 3, 24), cmplwi(11, 4), bge('db_done'),      # r11 = door
        *sc(12), addi(12, 12, FLAGS), lbzx(12, 12, 11),        # flag[door]
        cmplwi(12, 0), beq('db_done'),
        lis(12, DOORS_HI), ori(12, 12, DOORS_LO),
        mulli(11, 11, 0x24), add(12, 12, 11),  # r12 = door
        *sc(11), lwz(11, P_SELNONE, 11),
        stb(11, 0xE, 12),                      # sel_icon = sentinel -> DB34 draws blank
        label('db_done'),
    ])


# ======================================================================
# no_summon @ 0x802621DC  (hover-summon sel load; orig `lbzx r0,r8,r5`)
# When the hand hovers the grid with no pick, the game summons the coin to
# the hand. For an armed door that would unpark the mystery coin, so report
# "has a pick" (r0 = 0). Scoped to the hand being above the card band so the
# card UI (which shares this load) still sees "no pick".
# ======================================================================
def no_summon():
    return asm([
        raw(0x7C0828AE),                       # orig lbzx r0, r8, r5  (r6=port)
        *sc(11), lwz(12, P_SELNONE, 11), cmplw(0, 12), bne('done'),
        addi(12, 11, FLAGS), lbzx(12, 12, 6),
        cmplwi(12, 0), beq('done'),
        lis(11, HAND_HI), ori(11, 11, HAND_LO),
        rlwinm(12, 6, 2, 0, 29), lwzx(11, 11, 12),
        cmplwi(11, 0), beq('done'),
        lwz(11, 0x10, 11), lis(12, 0xBF80),
        cmplw(11, 12), bgt('done'),            # hand y < -1 (card band): leave
        addi(0, 0, 0),                         # r0 = 0 -> no summon
        label('done'),
    ])


# ======================================================================
# pickup @ 0x802620C8  (B-pickup sel load; orig `lbzx r0,r8,r6`, r7=port)
# B reclaims the parked mystery coin: report "has a pick" so the native
# pickup proceeds, and clear the flag (cancel the mystery).
# ======================================================================
def pickup():
    return asm([
        raw(0x7C0830AE),                       # orig lbzx r0, r8, r6
        lbz(11, -0x49AA, 13), cmplwi(11, 0), bne('done'),     # sub-screen open
        *sc(11),
        lbz(12, PREV_PEND, 11), cmplwi(12, 0), bne('done'),  # ..or at frame start
        lwz(12, P_SELNONE, 11), cmplw(0, 12), bne('done'),
        addi(12, 11, FLAGS), lbzx(12, 12, 7),
        cmplwi(12, 0), beq('done'),
        addi(12, 11, FLAGS), addi(10, 0, 0), stbx(10, 12, 7),  # flag = 0
        addi(0, 0, 0),                         # r0 = 0 -> pickup proceeds
        label('done'),
    ])


def all_hooks():
    """(name, inject address, body words). Each body replaces the
    instruction at the address (C2 semantics) and re-emits the original
    where the function must continue."""
    return [
        ("RandomPool RollFilter", 0x8025FB74, roll_filter()),
        ("RandomPool CssFrame",   0x80266A0C, css_frame()),
        ("RandomPool CssEnter",   0x8026688C, css_enter()),
        ("RandomPool ArmGate",    0x802609F4, arm_gate()),
        ("RandomPool Ready",      0x8026304C, ready()),
        ("RandomPool GateForce",  0x80263250, gate_force()),
        ("RandomPool DbBlank",    0x8025DB34, db_blank()),
        ("RandomPool CursorOk",   0x80263108, cursor_ok()),
        ("RandomPool NoSummon",   0x802621DC, no_summon()),
        ("RandomPool Pickup",     0x802620C8, pickup()),
    ]


if __name__ == "__main__":
    codes = [(name, c2(addr, body)) for name, addr, body in all_hooks()]
    dist = (sys.argv[1] if len(sys.argv) > 1
            else os.path.join(os.path.dirname(__file__), "..", "dist"))
    os.makedirs(dist, exist_ok=True)
    from geckogen import emit_gct
    emit_ini(codes, os.path.join(dist, "GALE01.ini"))    # regular Dolphin
    emit_ini(codes, os.path.join(dist, "GALE01r2.ini"))  # Slippi / 1.02 (rev r2)
    emit_gct(codes, os.path.join(dist, "GALE01.gct"))    # Nintendont console
    total = sum(len(lines) for _, lines in codes)
    for name, lines in codes:
        print(f"{name}: {len(lines)} lines")
    print(f"total {total} lines = {total * 8} bytes -> {dist}")
