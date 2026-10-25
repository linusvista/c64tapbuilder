#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C64 TAP Builder - c64tap.py

Genera un file .tap per Commodore 64 che contiene:
  1) un bootstrap BASIC caricato a velocita' normale dal KERNAL (stage 1)
  2) un turbo loader in linguaggio macchina 6502, guidato da interrupt (FLAG del CIA1)
  3) una schermata di caricamento con barra di avanzamento, titolo arcobaleno e musica
     (file .sid, musica predefinita interna oppure nessuna musica)
  4) il tuo PRG, diviso in blocchi turbo con checksum
  5) bordo e barra di avanzamento sincronizzati con i dati in arrivo dal nastro

Non servono assembler o librerie esterne: contiene un mini-assembler 6502 e un emulatore
6502 (usato per rilocare e verificare le tune SID). L'interfaccia grafica usa tkinter.

Uso:  python3 c64tap.py            (apre l'interfaccia grafica)
      python3 c64tap.py gioco.prg  (riga di comando, vedi --help)

Licenza: MIT (vedi il file LICENSE)
"""
__version__ = "1.0.0"
import argparse
import json
import os
import re
import struct
import sys
import types

OPS = {
    'adc': {'abs': 0x6D, 'abx': 0x7D, 'aby': 0x79, 'imm': 0x69, 'inx': 0x61, 'iny': 0x71, 'zpg': 0x65, 'zpx': 0x75},
    'and': {'abs': 0x2D, 'abx': 0x3D, 'aby': 0x39, 'imm': 0x29, 'inx': 0x21, 'iny': 0x31, 'zpg': 0x25, 'zpx': 0x35},
    'asl': {'abs': 0x0E, 'abx': 0x1E, 'acc': 0x0A, 'zpg': 0x06, 'zpx': 0x16},
    'bcc': {'rel': 0x90},
    'bcs': {'rel': 0xB0},
    'beq': {'rel': 0xF0},
    'bit': {'abs': 0x2C, 'zpg': 0x24},
    'bmi': {'rel': 0x30},
    'bne': {'rel': 0xD0},
    'bpl': {'rel': 0x10},
    'brk': {'imp': 0x00},
    'bvc': {'rel': 0x50},
    'bvs': {'rel': 0x70},
    'clc': {'imp': 0x18},
    'cld': {'imp': 0xD8},
    'cli': {'imp': 0x58},
    'clv': {'imp': 0xB8},
    'cmp': {'abs': 0xCD, 'abx': 0xDD, 'aby': 0xD9, 'imm': 0xC9, 'inx': 0xC1, 'iny': 0xD1, 'zpg': 0xC5, 'zpx': 0xD5},
    'cpx': {'abs': 0xEC, 'imm': 0xE0, 'zpg': 0xE4},
    'cpy': {'abs': 0xCC, 'imm': 0xC0, 'zpg': 0xC4},
    'dec': {'abs': 0xCE, 'abx': 0xDE, 'zpg': 0xC6, 'zpx': 0xD6},
    'dex': {'imp': 0xCA},
    'dey': {'imp': 0x88},
    'eor': {'abs': 0x4D, 'abx': 0x5D, 'aby': 0x59, 'imm': 0x49, 'inx': 0x41, 'iny': 0x51, 'zpg': 0x45, 'zpx': 0x55},
    'inc': {'abs': 0xEE, 'abx': 0xFE, 'zpg': 0xE6, 'zpx': 0xF6},
    'inx': {'imp': 0xE8},
    'iny': {'imp': 0xC8},
    'jmp': {'abs': 0x4C, 'ind': 0x6C},
    'jsr': {'abs': 0x20},
    'lda': {'abs': 0xAD, 'abx': 0xBD, 'aby': 0xB9, 'imm': 0xA9, 'inx': 0xA1, 'iny': 0xB1, 'zpg': 0xA5, 'zpx': 0xB5},
    'ldx': {'abs': 0xAE, 'aby': 0xBE, 'imm': 0xA2, 'zpg': 0xA6, 'zpy': 0xB6},
    'ldy': {'abs': 0xAC, 'abx': 0xBC, 'imm': 0xA0, 'zpg': 0xA4, 'zpx': 0xB4},
    'lsr': {'abs': 0x4E, 'abx': 0x5E, 'acc': 0x4A, 'zpg': 0x46, 'zpx': 0x56},
    'nop': {'imp': 0xEA},
    'ora': {'abs': 0x0D, 'abx': 0x1D, 'aby': 0x19, 'imm': 0x09, 'inx': 0x01, 'iny': 0x11, 'zpg': 0x05, 'zpx': 0x15},
    'pha': {'imp': 0x48},
    'php': {'imp': 0x08},
    'pla': {'imp': 0x68},
    'plp': {'imp': 0x28},
    'rol': {'abs': 0x2E, 'abx': 0x3E, 'acc': 0x2A, 'zpg': 0x26, 'zpx': 0x36},
    'ror': {'abs': 0x6E, 'abx': 0x7E, 'acc': 0x6A, 'zpg': 0x66, 'zpx': 0x76},
    'rti': {'imp': 0x40},
    'rts': {'imp': 0x60},
    'sbc': {'abs': 0xED, 'abx': 0xFD, 'aby': 0xF9, 'imm': 0xE9, 'inx': 0xE1, 'iny': 0xF1, 'zpg': 0xE5, 'zpx': 0xF5},
    'sec': {'imp': 0x38},
    'sed': {'imp': 0xF8},
    'sei': {'imp': 0x78},
    'sta': {'abs': 0x8D, 'abx': 0x9D, 'aby': 0x99, 'inx': 0x81, 'iny': 0x91, 'zpg': 0x85, 'zpx': 0x95},
    'stx': {'abs': 0x8E, 'zpg': 0x86, 'zpy': 0x96},
    'sty': {'abs': 0x8C, 'zpg': 0x84, 'zpx': 0x94},
    'tax': {'imp': 0xAA},
    'tay': {'imp': 0xA8},
    'tsx': {'imp': 0xBA},
    'txa': {'imp': 0x8A},
    'txs': {'imp': 0x9A},
    'tya': {'imp': 0x98},
}

# ---------------------------------------------------------------------------
# Mini assembler 6502 (due passate, etichette, espressioni semplici)
# ---------------------------------------------------------------------------
BRANCHES = {"bcc", "bcs", "beq", "bmi", "bne", "bpl", "bvc", "bvs"}


class AsmError(Exception):
    pass


class Assembler:
    def __init__(self, symbols=None):
        self.sym = dict(symbols or {})
        self.segs = []          # lista di (indirizzo, bytearray)

    # -- valutazione espressioni -------------------------------------------
    def _ev(self, expr, final):
        e = expr.strip()
        sel = None
        if e[:1] in "<>":
            sel, e = e[0], e[1:]
        e = re.sub(r"\$([0-9a-fA-F]+)", r"0x\1", e)
        known = [True]

        def repl(m):
            n = m.group(0)
            if n.startswith("0x"):
                return n
            if n in self.sym:
                return str(self.sym[n])
            if final:
                raise AsmError("simbolo sconosciuto: " + n)
            known[0] = False
            return "0"

        e = re.sub(r"\b0x[0-9a-fA-F]+\b|[A-Za-z_][A-Za-z0-9_]*", repl, e)
        v = int(eval(e, {"__builtins__": {}}, {}))
        if sel == "<":
            v &= 0xFF
        elif sel == ">":
            v = (v >> 8) & 0xFF
        return v, known[0]

    def _parse(self, src):
        rows = []
        for n, line in enumerate(src.splitlines()):
            line = line.split(";")[0].rstrip()
            if not line.strip():
                continue
            label = None
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", line.strip())
            if m:
                rows.append((n, None, "=", m.group(1) + "|" + m.group(2)))
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", line)
            if m:
                label, line = m.group(1), m.group(2)
            line = line.strip()
            if not line:
                rows.append((n, label, "", ""))
                continue
            parts = line.split(None, 1)
            rows.append((n, label, parts[0].lower(), parts[1].strip() if len(parts) > 1 else ""))
        return rows

    def run(self, src):
        rows = self._parse(src)
        self.modes = {}
        for final in (False, True):
            pc = None
            self.segs = []
            cur = None
            for n, label, mn, op in rows:
                if mn == "=":
                    name, ex = op.split("|", 1)
                    self.sym[name] = self._ev(ex, final)[0]
                    continue
                if label:
                    if pc is None:
                        raise AsmError("etichetta prima di .org")
                    self.sym[label] = pc
                if not mn:
                    continue
                if mn == ".org":
                    pc = self._ev(op, final)[0]
                    cur = bytearray()
                    self.segs.append((pc, cur))
                    continue
                if pc is None:
                    raise AsmError(".org mancante")
                data = self._emit(n, mn, op, pc, final)
                cur.extend(data)
                pc += len(data)
        return self.segs

    def _emit(self, n, mn, op, pc, final):
        if mn == ".byte":
            return bytes(self._ev(x, final)[0] & 0xFF for x in op.split(","))
        if mn == ".word":
            out = bytearray()
            for x in op.split(","):
                v = self._ev(x, final)[0]
                out += bytes((v & 255, (v >> 8) & 255))
            return bytes(out)
        if mn == ".fill":
            a, b = op.split(",")
            return bytes([self._ev(b, final)[0] & 255]) * self._ev(a, final)[0]
        if mn not in OPS:
            raise AsmError("istruzione sconosciuta: %s (riga %d)" % (mn, n))
        t = OPS[mn]
        op = op.strip()
        if not op:
            return bytes([t["imp"] if "imp" in t else t["acc"]])
        if op.lower() == "a" and "acc" in t:
            return bytes([t["acc"]])
        if mn in BRANCHES:
            tgt = self._ev(op, final)[0]
            off = tgt - (pc + 2)
            if final and not -128 <= off <= 127:
                raise AsmError("branch fuori portata riga %d (%s %s)" % (n, mn, op))
            return bytes([t["rel"], off & 255])
        if op.startswith("#"):
            return bytes([t["imm"], self._ev(op[1:], final)[0] & 255])
        m = re.match(r"^\((.+)\)\s*,\s*[yY]$", op)
        if m:
            return bytes([t["iny"], self._ev(m.group(1), final)[0] & 255])
        m = re.match(r"^\((.+)\s*,\s*[xX]\)$", op)
        if m:
            return bytes([t["inx"], self._ev(m.group(1), final)[0] & 255])
        m = re.match(r"^\((.+)\)$", op)
        if m:
            v = self._ev(m.group(1), final)[0]
            return bytes([t["ind"], v & 255, (v >> 8) & 255])
        idx = ""
        m = re.match(r"^(.+),\s*([xXyY])$", op)
        if m:
            op, idx = m.group(1), m.group(2).lower()
        v, known = self._ev(op, final)
        if not final:
            self.modes[n] = "zpg" if (known and v < 256) else "abs"
        zp = self.modes.get(n, "abs") == "zpg"
        if idx == "x":
            mode = "zpx" if zp and "zpx" in t else "abx"
        elif idx == "y":
            mode = "zpy" if zp and "zpy" in t else "aby"
        else:
            mode = "zpg" if zp and "zpg" in t else "abs"
        if mode not in t:
            raise AsmError("modo non valido riga %d: %s %s" % (n, mn, op))
        if mode in ("zpg", "zpx", "zpy"):
            return bytes([t[mode], v & 255])
        return bytes([t[mode], v & 255, (v >> 8) & 255])
# ---------------------------------------------------------------------------
# Sorgenti 6502
# ---------------------------------------------------------------------------

# Stage 1: programma BASIC "10 SYS2061" caricato dal KERNAL a velocita' normale.
# Copia il turbo loader (core) a BASE e lo avvia.
STAGE1_SRC = """
        .org $0801
        .byte $0b,$08,$0a,$00,$9e,$32,$30,$36,$31,$00,$00,$00
        sei
        lda #0
        sta $d020
        sta $d021
        lda #<src
        sta $fb
        lda #>src
        sta $fc
        lda #<BASE
        sta $fd
        lda #>BASE
        sta $fe
        ldx #NPAGES
        ldy #0
cl:     lda ($fb),y
        sta ($fd),y
        iny
        bne cl
        inc $fc
        inc $fe
        dex
        bne cl
        jmp BASE
src:
"""

# Core: ricevitore turbo guidato da interrupt FLAG del CIA1.
CORE_SRC = """
        .org BASE
sa      = ZB+$17
sx      = ZB+$18
sy      = ZB+$19
prev    = ZB+$1a
bits    = ZB+$1b
bcnt    = ZB+$1c
st      = ZB+$1d
ptr     = ZB+$1e
ready   = ZB
done    = ZB+1
err     = ZB+2
chunks  = ZB+3
mready  = ZB+4
bcol    = ZB+5
minit   = ZB+6
lastc   = ZB+7
pcount  = ZB+8
chk     = ZB+9
rem     = ZB+10
flags   = ZB+11
cslo    = ZB+12
cshi    = ZB+13
go_lo   = ZB+14
m0      = ZB+$10
m1      = ZB+$11
m2      = ZB+$12
m3      = ZB+$13
m4      = ZB+$14

core:   sei
        lda #<irq
        sta $fffe
        lda #>irq
        sta $ffff
        lda #<nmi
        sta $fffa
        lda #>nmi
        sta $fffb
        lda #$7f
        sta $dc0d
        sta $dd0d
        lda $dc0d
        lda $dd0d
        lda #0
        sta $d01a
        sta $d021
        lda #$ff
        sta $d019
        ldx #$1f
        lda #0
zc:     sta ZB,x
        dex
        bpl zc
        lda #2
        sta bcol
        lda #7
        sta $dc04
        lda #0
        sta $dc05
        lda #$ff
        sta $dc06
        sta $dc07
        lda #$11
        sta $dc0e
        lda #$51
        sta $dc0f
        lda #$15
        sta $01
        lda #$90
        sta $dc0d
        cli
wait:   lda ready
        beq wait
        jmp (go_lo)
nmi:    rti

irq:    sta sa
        lda $dc0d
        stx sx
        lda $dc06
        tax
        eor #$ff
        sec
        adc prev
        stx prev
        cmp #PTHR
        bcs pil
        ldx st
        beq hunt
        cmp #BTHR
        rol bits
        dec bcnt
        beq bytedone
fin:    ldx sx
        lda sa
        rti

pil:    ldx st
        bne bad
        ldx pcount
        cpx #MINP
        bcs pil2
        inc pcount
pil2:   lda bcol
        eor #1
        sta bcol
        sta $d020
        jmp fin
bad:    lda #0
        sta st
        sta pcount
        inc err
        jmp fin

hunt:   ldx pcount
        cpx #MINP
        bcc nopil
        ldx #1
        stx st
        ldx #8
        stx bcnt
        ldx #0
        stx bits
        cmp #BTHR
        rol bits
        dec bcnt
        jmp fin
nopil:  ldx #0
        stx pcount
        jmp fin

bytedone:
        lda #8
        sta bcnt
        sty sy
        lda bits
        sta $d020
        ldx st
        cpx #6
        beq pdata
        bcs pchk
        cpx #1
        beq pmark
        cpx #2
        beq plo
        cpx #3
        beq phi
        cpx #4
        beq plen
        sta flags
        eor chk
        sta chk
        lda #6
        sta st
bdone:  ldy sy
        jmp fin

pdata:  ldy #0
        sta (ptr),y
        eor chk
        sta chk
        inc ptr
        bne pd2
        inc ptr+1
pd2:    dec rem
        bne bdone
        lda #7
        sta st
        jmp bdone

pmark:  cmp #MARK
        bne rsync
        lda #0
        sta chk
        lda #2
        sta st
        jmp bdone
rsync:  lda #0
        sta st
        sta pcount
        jmp bdone

plo:    sta ptr
        sta cslo
        eor chk
        sta chk
        lda #3
        sta st
        jmp bdone
phi:    sta ptr+1
        sta cshi
        eor chk
        sta chk
        lda #4
        sta st
        jmp bdone
plen:   sta rem
        eor chk
        sta chk
        lda #5
        sta st
        jmp bdone

pchk:   cmp chk
        bne cerr
        inc chunks
        lda flags
        and #2
        beq nomr
        sta mready
nomr:   lda flags
        lsr
        bcc nogo
        ldx cslo
        stx go_lo
        ldx cshi
        stx go_lo+1
        ldx #1
        stx ready
nogo:   lda flags
        bpl nodn
        ldx #1
        stx done
nodn:   lda #0
        sta st
        sta pcount
        jmp bdone
cerr:   inc err
        lda #0
        sta st
        sta pcount
        jmp bdone

s2_stub: .byte $4c,0,0
core_end:
"""
# ---------------------------------------------------------------------------
# Musica interna (3 voci SID) + driver
# ---------------------------------------------------------------------------
PAL_CLOCK = 985248.0


def sid_freq(midi):
    f = 440.0 * 2 ** ((midi - 69) / 12.0)
    return min(65535, int(round(f * 16777216.0 / PAL_CLOCK)))


NOTE_OFF = 20   # byte nota = midi - 20  (0 = pausa)


def builtin_tune(step=6):
    """Loop di 4 battute Am-F-C-G: lead arpeggiato, basso, rullante/hat a rumore."""
    chords = [(45, (57, 60, 64)), (41, (53, 57, 60)), (48, (60, 64, 67)), (43, (55, 59, 62))]
    lead, bass, perc = [], [], []
    for bar, (root, tri) in enumerate(chords):
        up = 12 if bar % 2 else 0
        c0, c1, c2 = (n + 12 + up for n in tri)
        for n in (c0, c1, c2, c1, c2, c1, c0, c1):
            lead.append((n - NOTE_OFF, step))
        for o in (0, 12, 0, 12):
            bass.append((root + o - NOTE_OFF, step * 2))
        for i in range(8):
            perc.append((88 - NOTE_OFF if i % 2 == 0 else 80 - NOTE_OFF, step) if i % 4 != 2
                        else (96 - NOTE_OFF, step))
    ev = lambda lst: [b for n, d in lst for b in (n, d)] + [0xFF]
    return ev(lead), ev(bass), ev(perc)


MUSIC_SRC = """
vplo:   .byte 0,0,0
vphi:   .byte 0,0,0
vcnt:   .byte 1,1,1
voff:   .byte 0,7,14
vwave:  .byte $40,$20,$80
vsl:    .byte <tune0,<tune1,<tune2
vsh:    .byte >tune0,>tune1,>tune2
music_init:
        ldx #$18
        lda #0
mi0:    sta $d400,x
        dex
        bpl mi0
        lda #$0f
        sta $d418
        lda #$08
        sta $d403
        lda #$09
        sta $d405
        lda #$a6
        sta $d406
        lda #$08
        sta $d40c
        lda #$b0
        sta $d40d
        lda #$01
        sta $d413
        lda #$00
        sta $d414
        ldx #2
mi1:    lda vsl,x
        sta vplo,x
        lda vsh,x
        sta vphi,x
        lda #1
        sta vcnt,x
        dex
        bpl mi1
        rts
music_play:
        ldx #2
mp0:    stx m4
        dec vcnt,x
        beq mpf
        lda vcnt,x
        cmp #1
        bne mpn
        ldy voff,x
        lda vwave,x
        sta $d404,y
        jmp mpn
mpf:    lda vplo,x
        sta m0
        lda vphi,x
        sta m1
        ldy #0
        lda (m0),y
        cmp #$ff
        bne mph
        lda vsl,x
        sta m0
        lda vsh,x
        sta m1
mph:    ldy #0
        lda (m0),y
        sta m2
        iny
        lda (m0),y
        sta m3
        clc
        lda m0
        adc #2
        sta vplo,x
        lda m1
        adc #0
        sta vphi,x
        lda m3
        sta vcnt,x
        ldy voff,x
        lda m2
        beq mpr
        tax
        lda ftlo,x
        sta $d400,y
        lda fthi,x
        sta $d401,y
        ldx m4
        lda vwave,x
        ora #1
        sta $d404,y
        jmp mpn
mpr:    ldx m4
        lda vwave,x
        sta $d404,y
mpn:    ldx m4
        dex
        bmi mpe
        jmp mp0
mpe:    rts
"""

SID_WRAP_SRC = """
music_init:
        lda #SID_SONG
        jmp SID_INIT
music_play:
        jmp SID_PLAY
"""


CREDIT = "(c) MMXXVI Loader by Linusvista"
DESC_LINES = 10         # righe della descrizione
SCROLL_WIN = 38         # larghezza massima di una riga (colonne)
DESC_WIDTH = SCROLL_WIN
SCROLL_MAX = DESC_LINES * DESC_WIDTH      # 380 caratteri in tutto
PAGE_FRAMES = 250       # durata di ogni riga a video (250 frame = 5 s a 50 Hz)


def wrap_desc(text):
    """Spezza la descrizione in righe da al massimo SCROLL_WIN caratteri, andando a capo tra le parole."""
    import textwrap
    text = " ".join(text.split())
    return textwrap.wrap(text, SCROLL_WIN, break_long_words=True, break_on_hyphens=False) or []


def raw_desc_lines(text):
    """Righe 'grezze' della descrizione: separate da a capo (o '|' da riga di comando), vuote ignorate."""
    return [p.strip() for p in (text or "").replace("|", "\n").split("\n") if p.strip()]


def desc_lines(text):
    """Righe da mostrare a video (max DESC_LINES da DESC_WIDTH caratteri). Se c'e' una sola riga piu' lunga
    di DESC_WIDTH viene spezzata fra le parole."""
    parts = raw_desc_lines(text)
    if len(parts) == 1 and len(parts[0]) > DESC_WIDTH:
        parts = wrap_desc(parts[0])
    return [p[:DESC_WIDTH] for p in parts][:DESC_LINES]


def text_to_screen(s):
    """ASCII -> screen code del set di caratteri maiuscole/minuscole ($D018=$17)."""
    out = []
    for ch in s:
        o = ord(ch)
        if 65 <= o <= 90:
            out.append(o)              # maiuscole = 65-90
        elif 97 <= o <= 122:
            out.append(o - 96)         # minuscole = 1-26
        elif 32 <= o <= 63:
            out.append(o)
        elif ch == "@":
            out.append(0)
        else:
            out.append(32)
    return out


def bytes_src(label, data):
    lines = [label + ":"]
    for i in range(0, len(data), 16):
        lines.append("        .byte " + ",".join(str(b) for b in data[i:i + 16]))
    return "\n".join(lines)


def stage2_source(cfg):
    """Genera il sorgente dello stage 2 (UI + musica + finish)."""
    texts = []     # (nome, riga, testo)
    t_title = cfg["title"][:38]
    texts.append(("t_title", 7, t_title))
    texts.append(("t_load", 10, "CARICAMENTO..."))
    texts.append(("t_cred", 2, CREDIT))
    lines = desc_lines(cfg["subtitle"])
    scroll = len(lines) > 1          # piu' righe: mostrate una alla volta
    if len(lines) == 1:
        texts.append(("t_sub", 22, lines[0]))
    s = []
    a = s.append
    a("s2_start:")
    a("s2_main:")
    a("""        lda #$17
        sta $d018
        lda $d011
        and #$7f
        sta $d011
        lda #$fa
        sta $d012
        lda #0
        sta $d021
        ldx #0
        lda #$20
cs:     sta $0400,x
        sta $0500,x
        sta $0600,x
        sta $06e8,x
        inx
        bne cs
        ldx #0
        lda #1
cc:     sta $d800,x
        sta $d900,x
        sta $da00,x
        sta $dae8,x
        inx
        bne cc
        ldx #31
        lda #3
bc:     sta $d800+14*40+4,x
        dex
        bpl bc
        lda #$1b
        sta $0400+14*40+3
        lda #$1d
        sta $0400+14*40+36
        lda #$25
        sta $0400+16*40+21
        ldx #39
hl:     lda #$40
        sta $0400+160,x
        sta $0400+800,x
        dex
        bpl hl""")
    for name, row, txt in texts:
        n = len(txt)
        col = (40 - n) // 2
        a("""        ldx #0
%s_l:  lda %s,x
        sta $0400+%d,x
        inx
        cpx #%d
        bne %s_l""" % (name, name, row * 40 + col, n, name))
        if name == "t_sub":
            a("""        ldx #%d
%s_c:  lda #11
        sta $d800+%d,x
        dex
        bpl %s_c""" % (n - 1, name, row * 40 + col, name))
    if scroll:
        a("""        lda #<t_pg
        sta pglo
        lda #>t_pg
        sta pghi
        lda #1
        sta pgt
        ldx #39
scc:    lda #11
        sta $d800+22*40,x
        dex
        bpl scc""")
    if cfg["music"] == "default":
        a("""        jsr music_init
        lda #1
        sta mready
        sta minit""")
    a("""loop:   jsr wait_raster
        jsr mus_frame
        jsr cyc
        SCROLLCALL
        jsr upd
        inc idlelo
        bne il1
        inc idlehi
il1:    lda idlehi
        cmp #2
        bcc il2
        lda err
        beq il2
        jmp lerr
il2:    lda done
        beq loop
        jsr upd
        lda #40
        sta tgt
fl2:    jsr wait_raster
        jsr mus_frame
        jsr cyc
        dec tgt
        bne fl2
        lda chunks
        cmp #NTOT
        beq fin_ok
        jmp lerr
fin_ok: jmp finish

wait_raster:
wr:     lda $d019
        and #1
        beq wr
        lda #1
        sta $d019
        rts

mus_frame:
        lda mready
        beq mf_end
        lda minit
        bne mf_play
        jsr music_init
        lda #1
        sta minit
        rts
mf_play:
        jsr music_play
mf_end: rts

cyc:    inc frame
        lda frame
        lsr
        lsr
        sta cyt
        ldx #39
cl:     txa
        clc
        adc cyt
        and #7
        tay
        lda rbtab,y
        sta $d800+160,x
        sta $d800+280,x
        sta $d800+800,x
        dex
        bpl cl
        rts

upd:    ldx chunks
        cpx lastc
        beq upd_end
        stx lastc
        lda #0
        sta idlelo
        sta idlehi
        lda bar_tab,x
        sta tgt2
pbl:    ldy barcur
        cpy tgt2
        bcs pend
        lda #$a0
        sta $0400+14*40+4,y
        inc barcur
        jmp pbl
pend:   lda pct_tab,x
        ldy #0
        cmp #100
        bne plt
        lda #$31
        sta $0400+16*40+18
        lda #$30
        sta $0400+16*40+19
        sta $0400+16*40+20
        rts
plt:    cmp #10
        bcc pu
        sbc #10
        iny
        bne plt
pu:     clc
        adc #$30
        sta $0400+16*40+20
        tya
        clc
        adc #$30
        sta $0400+16*40+19
        lda #$20
        sta $0400+16*40+18
upd_end: rts

lerr:   sei
        lda #0
        sta $d418
        lda #2
        sta $d020
        ldx #0
le1:    lda t_err,x
        sta $0400+18*40+9,x
        inx
        cpx #21
        bne le1
        ldx #19
le2:    lda t_diag,x
        sta $0400+20*40+10,x
        dex
        bpl le2
        lda chunks
        ldy #8
        jsr hexp
        lda #NTOT
        ldy #11
        jsr hexp
        lda err
        ldy #18
        jsr hexp
lhang:  jmp lhang

hexp:   pha
        lsr
        lsr
        lsr
        lsr
        jsr hnib
        sta $0400+20*40+10,y
        pla
        and #$0f
        jsr hnib
        sta $0400+20*40+11,y
        rts
hnib:   cmp #10
        bcc hn1
        sbc #9
        ora #$40
        rts
hn1:    ora #$30
        rts

""")
    # finish
    a("""finish: sei
        lda #$7f
        sta $dc0d
        lda $dc0d
        lda #0
        ldx #$18
fz:     sta $d400,x
        dex
        bpl fz
        lda #$37
        sta $01
        jsr $fda3
        jsr $fd15
        jsr $ff5b
        lda #<END_ADDR
        sta $2d
        sta $2f
        sta $31
        lda #>END_ADDR
        sta $2e
        sta $30
        sta $32""")
    if cfg["run_mode"] == "sys":
        a("""        cli
        jmp RUN_ADDR""")
    else:
        a("""        lda #$52
        sta $0277
        lda #$55
        sta $0278
        lda #$4e
        sta $0279
        lda #$0d
        sta $027a
        lda #4
        sta $c6
        cli
        jmp $a474""")
    a("""frame:  .byte 0
idlelo: .byte 0
idlehi: .byte 0
cyt:    .byte 0
tgt:    .byte 0
tgt2:   .byte 0
barcur: .byte 0
rbtab:  .byte 2,8,7,5,3,14,4,10""")
    a(bytes_src("t_err", text_to_screen("ERRORE DI CARICAMENTO")))
    a(bytes_src("t_diag", text_to_screen("BLOCCHI 00/00 ERR 00")))
    for name, row, txt in texts:
        a(bytes_src(name, text_to_screen(txt)))
    if scroll:
        a("""pager:  dec pgt
        bne pg_end
        lda #%d
        sta pgt
        lda pglo
        sta m0
        lda pghi
        sta m1
        ldy #39
pg1:    lda (m0),y
        sta $0400+22*40,y
        dey
        bpl pg1
        clc
        lda pglo
        adc #40
        sta pglo
        lda pghi
        adc #0
        sta pghi
        lda pglo
        cmp #<pg_endd
        bne pg_end
        lda pghi
        cmp #>pg_endd
        bne pg_end
        lda #<t_pg
        sta pglo
        lda #>t_pg
        sta pghi
pg_end: rts
pglo:   .byte 0
pghi:   .byte 0
pgt:    .byte 1""" % PAGE_FRAMES)
        rows = []
        for ln in lines:
            row = [32] * 40
            codes = text_to_screen(ln)
            c0 = (40 - len(codes)) // 2
            row[c0:c0 + len(codes)] = codes
            rows += row
        a(bytes_src("t_pg", rows))
        a("pg_endd:")
    a(bytes_src("bar_tab", cfg["bar_tab"]))
    a(bytes_src("pct_tab", cfg["pct_tab"]))
    if cfg["music"] == "sid":
        a(SID_WRAP_SRC)
    elif cfg["music"] == "none":
        a("music_init:\n        rts\nmusic_play:\n        rts")
    else:
        lead, bass, perc = builtin_tune()
        ns = range(NOTE_OFF + 1, 100)
        a(MUSIC_SRC)
        a(bytes_src("tune0", lead))
        a(bytes_src("tune1", bass))
        a(bytes_src("tune2", perc))
        freqs = [0] + [sid_freq(n) for n in range(NOTE_OFF + 1, 109)]
        a(bytes_src("ftlo", [f & 255 for f in freqs]))
        a(bytes_src("fthi", [f >> 8 for f in freqs]))
    a("s2_end:")
    return "\n".join(s).replace("        SCROLLCALL", "        jsr pager" if scroll else "")
# ---------------------------------------------------------------------------
# Formato TAP
# ---------------------------------------------------------------------------
K_S, K_M, K_L = 0x30, 0x42, 0x56     # impulsi standard KERNAL (PAL, unita' = 8 cicli)

SPEEDS = {   # (bit0, bit1, pilota) in unita' da 8 cicli di clock
    "slow": (0x26, 0x42, 0x5C),
    "normal": (0x1E, 0x34, 0x48),
    "fast": (0x1A, 0x2E, 0x3E),
}
MARK = 0xA5
MIN_PILOT = 24


class Tap:
    def __init__(self):
        self.d = bytearray()
        self.total = 0          # durata in cicli di clock

    def pulses(self, lst):
        self.d.extend(lst)
        self.total += sum(lst) * 8

    def pause(self, cycles):
        self.d.extend(b"\x00" + cycles.to_bytes(3, "little"))
        self.total += cycles

    def tobytes(self):
        return b"C64-TAPE-RAW" + bytes([1, 0, 0, 0]) + len(self.d).to_bytes(4, "little") + bytes(self.d)


def k_byte(b):
    par = 1 ^ (bin(b).count("1") & 1)
    p = [K_L, K_M]
    for i in range(8):
        p += [K_M, K_S] if (b >> i) & 1 else [K_S, K_M]
    p += [K_M, K_S] if par else [K_S, K_M]
    return p


def k_block(payload, leader):
    chk = 0
    for b in payload:
        chk ^= b
    out = [K_S] * leader
    for rep in (0, 1):
        sync = list(range(0x89, 0x80, -1)) if rep == 0 else list(range(9, 0, -1))
        for b in sync + list(payload) + [chk]:
            out += k_byte(b)
        out += [K_L, K_S]
        out += [K_S] * (79 if rep == 0 else 78)
    return out


def kernal_program(tap, name, load_addr, data, hdr_leader=3000, data_leader=1500):
    end = load_addr + len(data)
    hdr = bytearray([1, load_addr & 255, load_addr >> 8, end & 255, end >> 8])
    hdr += name.upper().encode("latin1")[:16].ljust(16, b" ")
    hdr += b" " * (192 - len(hdr))
    tap.pulses(k_block(hdr, hdr_leader))
    tap.pulses(k_block(data, data_leader))


def turbo_chunk(tap, speed, addr, data, flags, pilot_n):
    b0, b1, pil = SPEEDS[speed]
    n = len(data)
    assert 1 <= n <= 256
    body = [addr & 255, addr >> 8, n & 255, flags] + list(data)
    chk = 0
    for b in body:
        chk ^= b
    out = [pil] * pilot_n
    for b in [MARK] + body + [chk]:
        for i in range(7, -1, -1):
            out.append(b1 if (b >> i) & 1 else b0)
    tap.pulses(out)

# ---------------------------------------------------------------------------
# SID / PRG / controlli
# ---------------------------------------------------------------------------
DEFAULTS = dict(prg="", sid="", song=0, output="", name="LOADER", title="C64 TURBO LOADER",
                subtitle="", speed="normal", chunk=256, run=None, loader_addr=None,
                hdr_leader=4000, data_leader=2000, pause=2_000_000, first_pilot=600, chunk_pilot=32,
                sid_reloc="auto", music=None)

# chiave: (nome, parametri, descrizione)
PRESETS = {
    "emu-fast": ("Emulatore - veloce (VICE)", dict(
        speed="fast", chunk=256, hdr_leader=2000, data_leader=1000, pause=1_000_000,
        first_pilot=400, chunk_pilot=32),
        "Per VICE & co. Massima velocita'. Non adatto a un vero datassette."),
    "emu": ("Emulatore - standard", dict(
        speed="normal", chunk=256, hdr_leader=4000, data_leader=2000, pause=2_000_000,
        first_pilot=600, chunk_pilot=32),
        "Per emulatori e MiSTer/BMC64. Buon compromesso, tempi tipici del turbo su nastro."),
    "tape": ("Datassette originale - normale", dict(
        speed="normal", chunk=256, hdr_leader=8000, data_leader=4000, pause=3_000_000,
        first_pilot=1500, chunk_pilot=48),
        "Per un datassette in buone condizioni, testina pulita e nastro/WAV di qualita'."),
    "tape-safe": ("Datassette originale - sicuro", dict(
        speed="slow", chunk=128, hdr_leader=10000, data_leader=5000, pause=4_000_000,
        first_pilot=2500, chunk_pilot=64),
        "Per datassette vecchi o registrazioni su cassetta vera: lento ma tollerante."),
}
CUSTOM_PRESET = "Personalizzato"
TAPE_KEYS = ("speed", "chunk", "hdr_leader", "data_leader", "pause", "first_pilot", "chunk_pilot")


def make_opts(**kw):
    d = dict(DEFAULTS)
    d.update(kw)
    return types.SimpleNamespace(**d)


def parse_addr(s):
    s = str(s).strip()
    if not s:
        raise ValueError("vuoto")
    if s.startswith("$"):
        return int(s[1:], 16)
    return int(s, 0)


def hx(a):
    return "$%04X" % a


class Report:
    def __init__(self):
        self.items = []

    def add(self, lvl, msg):
        self.items.append((lvl, msg))

    @property
    def ok(self):
        return not any(l == "ERR" for l, _ in self.items)

    def text(self):
        sym = {"ERR": "ERRORE ", "WARN": "ATTENZIONE ", "INFO": "info "}
        return "\n".join("[%s] %s" % (l, m) for l, m in self.items)


def read_psid(path, song=None):
    raw = open(path, "rb").read()
    if raw[:4] == b"RSID":
        raise ValueError("RSID non supportato (serve un file PSID)")
    if raw[:4] != b"PSID" or len(raw) < 0x76:
        raise ValueError("non e' un file PSID valido")
    ver, off, load, init, play, songs, start = struct.unpack(">HHHHHHH", raw[4:18])
    speed = struct.unpack(">I", raw[18:22])[0]
    data = raw[off:]
    if load == 0:
        if len(data) < 2:
            raise ValueError("dati SID troncati")
        load = data[0] | (data[1] << 8)
        data = data[2:]
    if init == 0:
        init = load
    if play == 0:
        raise ValueError("play address = 0 (musica pilotata da IRQ proprio): non supportato")
    sg = (song if song else start) - 1
    if not 0 <= sg < songs:
        raise ValueError("traccia %d inesistente (il file ne contiene %d)" % (sg + 1, songs))
    cia = bool(speed >> min(sg, 31) & 1)
    return dict(load=load, data=data, init=init, play=play, song=sg, songs=songs, cia=cia)


def parse_sys(la, data):
    """Se il PRG inizia con 'N SYS xxxx' restituisce l'indirizzo, altrimenti None."""
    if la == 0x0801 and len(data) > 8 and data[4] == 0x9E:
        i, digits = 5, ""
        while i < len(data) and data[i] == 0x20:
            i += 1
        while i < len(data) and 0x30 <= data[i] <= 0x39:
            digits += chr(data[i])
            i += 1
        if digits:
            return int(digits)
    return None


def split_chunks(addr, data, size):
    return [(addr + o, data[o:o + size]) for o in range(0, len(data), size)]


def overlap(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


def free_windows(used, lo=0x0800, hi=0xD000):
    """Intervalli liberi (start, end) in [lo, hi) togliendo le zone usate."""
    win = [(lo, hi)]
    for s, e in sorted(used):
        new = []
        for a, b in win:
            if e <= a or s >= b:
                new.append((a, b))
                continue
            if s > a:
                new.append((a, s))
            if e < b:
                new.append((e, b))
        win = new
    return win


def fmt_windows(win, minsize=256, limit=4):
    big = sorted([w for w in win if w[1] - w[0] >= minsize], key=lambda w: w[0] - w[1])[:limit]
    return ", ".join("%s-%s (%d byte)" % (hx(a), hx(b - 1), b - a) for a, b in big) or "nessuna"


def check_prg(R, o):
    """Controlla il file PRG e restituisce (load_addr, data) oppure None."""
    if not o.prg:
        R.add("ERR", "Seleziona il file PRG di origine.")
        return None
    if not os.path.isfile(o.prg):
        R.add("ERR", "Il file PRG non esiste: " + o.prg)
        return None
    try:
        raw = open(o.prg, "rb").read()
    except OSError as e:
        R.add("ERR", "Impossibile leggere il PRG: %s" % e)
        return None
    ext = os.path.splitext(o.prg)[1].lower()
    if raw[:12] == b"C64-TAPE-RAW":
        R.add("ERR", "Il file e' gia' un .tap, non un PRG.")
        return None
    if raw[:4] in (b"PSID", b"RSID"):
        R.add("ERR", "Il file e' un SID: va messo nel campo Musica, non come PRG.")
        return None
    if raw[:15] == b"C64S tape image" or raw[:3] == b"C64" and ext == ".t64":
        R.add("ERR", "Il file e' un'immagine T64: estrai prima il PRG.")
        return None
    if len(raw) in (174848, 175531, 196608, 197376) or ext in (".d64", ".g64", ".d71", ".d81"):
        R.add("ERR", "Sembra un'immagine disco: estrai il PRG (es. con c1541) e selezionalo.")
        return None
    if ext in (".crt", ".tap", ".sid", ".t64"):
        R.add("ERR", "Estensione %s: serve un file PRG." % ext)
        return None
    if ext not in (".prg", ""):
        R.add("WARN", "Estensione insolita (%s): controllo comunque il contenuto." % ext)
    if len(raw) < 3:
        R.add("ERR", "File PRG vuoto o troppo corto.")
        return None
    la, data = raw[0] | (raw[1] << 8), raw[2:]
    gend = la + len(data)
    R.add("INFO", "PRG: %s-%s, %d byte (%d KB)." % (hx(la), hx(gend - 1), len(data), (len(data) + 1023) // 1024))
    if gend > 0x10000:
        R.add("ERR", "Il PRG supera $FFFF: i primi due byte (%s) non sembrano un indirizzo di caricamento valido." % hx(la))
        return None
    if la < 0x0200:
        R.add("ERR", "Indirizzo di caricamento %s troppo basso (zero page/stack). "
                     "Probabilmente non e' un vero PRG." % hx(la))
        return None
    if gend > 0xD000:
        R.add("ERR", "Il PRG arriva a %s: il tratto sopra $CFFF (I/O, KERNAL) non e' caricabile dal turbo. "
                     "Riduci il gioco o caricane la parte alta con un packer/self-extractor." % hx(gend - 1))
        return None
    if overlap(la, gend, 0x0400, 0x0800):
        R.add("ERR", "Il PRG (%s-%s) copre $0400-$07FF, la RAM schermo usata dal loader. "
                     "Fai partire il programma da $0801 o piu' in alto, oppure spostalo dopo $07FF."
              % (hx(la), hx(gend - 1)))
        return None
    if la < 0x0400 and gend > 0x0200:
        R.add("WARN", "Il PRG tocca $0200-$03FF (variabili KERNAL): il loader non ne soffre, "
                      "ma verifica che sia voluto.")
    return la, data


# ---------------------------------------------------------------------------
# Rilocazione SID: mini emulatore 6502 con tracciamento + verifica differenziale
# ---------------------------------------------------------------------------
LEN_MODE = {"imp": 1, "acc": 1, "imm": 2, "zpg": 2, "zpx": 2, "zpy": 2, "rel": 2, "inx": 2, "iny": 2,
            "abs": 3, "abx": 3, "aby": 3, "ind": 3}
INFO = {}
for _mn, _t in OPS.items():
    for _mode, _op in _t.items():
        INFO[_op] = (_mn, _mode)

SID_FRAMES = 6000       # frame (2 minuti) analizzati per il profilo della tune
SENTINEL = 0xFFF0


class EmuError(Exception):
    pass


class Cpu:
    """Emulatore 6502 (solo opcode ufficiali, niente modo decimale).
    Con track=(lo, hi) segue l'origine dei byte letti dalla tune per trovare i riferimenti ad indirizzo."""

    def __init__(self, mem, track=None):
        self.m = mem
        self.a = self.x = self.y = 0
        self.sp = 0xFF
        self.pc = 0
        self.n = self.v = self.z = self.c = self.d = 0
        self.i = 1
        self.rn = 0
        self.frame = 0
        self.sidw = []
        self.track = track
        self.tm = {}
        self.ta = self.tx = self.ty = None
        self.sites = set()
        self.zp = set()
        self.wset = set()
        self.watch = None
        self.hits = set()

    # -- memoria / I-O
    def rd(self, a):
        w = self.watch
        if w and w[0] <= a < w[1] and not w[2] <= a < w[3]:
            self.hits.add(a)
        if 0xD000 <= a < 0xE000:
            if a == 0xD012 or a == 0xD41B or a == 0xD41C:
                self.rn = (self.rn + 7) & 0xFF
                return self.rn
            if a >= 0xDC00 or a == 0xD019:
                return 0
        return self.m[a]

    def wr(self, a, v):
        if 0x200 <= a < 0xD000:
            self.wset.add(a)
            w = self.watch
            if w and w[0] <= a < w[1] and not w[2] <= a < w[3]:
                self.hits.add(a)
        if 0xD400 <= a <= 0xD41F:
            self.sidw.append((self.frame, a & 0x1F, v))
        self.m[a] = v

    def tag(self, a):
        if a in self.tm:
            return self.tm[a]
        lo, hi = self.track
        return a if lo <= a < hi else None

    def chk(self, hiaddr, *vals):
        t = self.tag(hiaddr)
        if t is not None:
            lo, hi = self.track
            for v in vals:
                if lo <= v < hi:
                    self.sites.add(t)
                    break

    def push(self, v):
        self.m[0x100 + self.sp] = v & 255
        self.sp = (self.sp - 1) & 255

    def pull(self):
        self.sp = (self.sp + 1) & 255
        return self.m[0x100 + self.sp]

    def getp(self, b):
        return (self.n << 7) | (self.v << 6) | 0x20 | b | (self.d << 3) | (self.i << 2) | (self.z << 1) | self.c

    def setp(self, p):
        self.n, self.v, self.d, self.i, self.z, self.c = (p >> 7) & 1, (p >> 6) & 1, (p >> 3) & 1, (p >> 2) & 1, (p >> 1) & 1, p & 1

    def nz(self, v):
        self.n = (v >> 7) & 1
        self.z = 1 if v == 0 else 0
        return v

    def adc(self, v):
        if self.d:
            raise EmuError("modo decimale non supportato")
        t = self.a + v + self.c
        self.v = 1 if (~(self.a ^ v) & (self.a ^ t) & 0x80) else 0
        self.c = 1 if t > 255 else 0
        self.a = self.nz(t & 255)

    def step(self):
        m = self.m
        pc = self.pc
        op = m[pc]
        try:
            mn, mode = INFO[op]
        except KeyError:
            raise EmuError("opcode non supportato $%02X a $%04X" % (op, pc))
        tr = self.track
        nxt = pc + LEN_MODE[mode]
        ea = None
        if mode == "imm":
            ea = pc + 1
        elif mode == "zpg":
            ea = m[pc + 1]
            self.zp.add(ea)
        elif mode == "zpx":
            ea = (m[pc + 1] + self.x) & 255
            self.zp.add(ea)
        elif mode == "zpy":
            ea = (m[pc + 1] + self.y) & 255
            self.zp.add(ea)
        elif mode in ("abs", "abx", "aby"):
            base = m[pc + 1] | (m[pc + 2] << 8)
            ea = base if mode == "abs" else (base + (self.x if mode == "abx" else self.y)) & 0xFFFF
            if tr:
                self.chk(pc + 2, base, ea)
        elif mode == "inx":
            zp = (m[pc + 1] + self.x) & 255
            self.zp.update((zp, (zp + 1) & 255))
            ea = m[zp] | (m[(zp + 1) & 255] << 8)
            if tr:
                self.chk((zp + 1) & 255, ea)
        elif mode == "iny":
            zp = m[pc + 1]
            self.zp.update((zp, (zp + 1) & 255))
            base = m[zp] | (m[(zp + 1) & 255] << 8)
            ea = (base + self.y) & 0xFFFF
            if tr:
                self.chk((zp + 1) & 255, base, ea)
        elif mode == "ind":
            ptr = m[pc + 1] | (m[pc + 2] << 8)
            ea = m[ptr] | (m[(ptr & 0xFF00) | ((ptr + 1) & 0xFF)] << 8)
            if tr:
                self.chk(pc + 2, ptr)
                self.chk((ptr & 0xFF00) | ((ptr + 1) & 0xFF), ea)
        elif mode == "rel":
            off = m[pc + 1]
            ea = nxt + (off - 256 if off > 127 else off)
        self.pc = nxt
        # ---- esecuzione
        if mn == "lda":
            self.a = self.nz(self.rd(ea))
            if tr: self.ta = self.tag(ea)
        elif mn == "sta":
            self.wr(ea, self.a)
            if tr: self.tm[ea] = self.ta
        elif mn == "ldx":
            self.x = self.nz(self.rd(ea))
            if tr: self.tx = self.tag(ea)
        elif mn == "ldy":
            self.y = self.nz(self.rd(ea))
            if tr: self.ty = self.tag(ea)
        elif mn == "stx":
            self.wr(ea, self.x)
            if tr: self.tm[ea] = self.tx
        elif mn == "sty":
            self.wr(ea, self.y)
            if tr: self.tm[ea] = self.ty
        elif mn in ("inx", "iny", "dex", "dey"):
            r = mn[2]
            d = 1 if mn[0] == "i" else -1
            if r == "x":
                self.x = self.nz((self.x + d) & 255)
            else:
                self.y = self.nz((self.y + d) & 255)
        elif mn in ("inc", "dec"):
            v = self.nz((self.rd(ea) + (1 if mn == "inc" else -1)) & 255)
            self.wr(ea, v)
        elif mn in ("bne", "beq", "bcc", "bcs", "bpl", "bmi", "bvc", "bvs"):
            f = {"bne": not self.z, "beq": self.z, "bcc": not self.c, "bcs": self.c, "bpl": not self.n,
                 "bmi": self.n, "bvc": not self.v, "bvs": self.v}[mn]
            if f:
                self.pc = ea
        elif mn == "jmp":
            self.pc = ea
        elif mn == "jsr":
            r = nxt - 1
            self.push(r >> 8)
            self.push(r & 255)
            self.pc = ea
        elif mn == "rts":
            lo = self.pull()
            self.pc = ((lo | (self.pull() << 8)) + 1) & 0xFFFF
        elif mn in ("cmp", "cpx", "cpy"):
            r = {"cmp": self.a, "cpx": self.x, "cpy": self.y}[mn]
            v = self.rd(ea)
            self.c = 1 if r >= v else 0
            self.nz((r - v) & 255)
        elif mn == "adc":
            self.adc(self.rd(ea))
        elif mn == "sbc":
            self.adc(self.rd(ea) ^ 0xFF)
        elif mn in ("and", "ora", "eor"):
            v = self.rd(ea)
            self.a = self.nz({"and": self.a & v, "ora": self.a | v, "eor": self.a ^ v}[mn])
            if tr: self.ta = None
        elif mn in ("asl", "lsr", "rol", "ror"):
            v = self.a if mode == "acc" else self.rd(ea)
            if mn == "asl":
                c, v = v >> 7, (v << 1) & 255
            elif mn == "lsr":
                c, v = v & 1, v >> 1
            elif mn == "rol":
                c, v = v >> 7, ((v << 1) | self.c) & 255
            else:
                c, v = v & 1, (v >> 1) | (self.c << 7)
            self.c = c
            self.nz(v)
            if mode == "acc":
                self.a = v
                if tr: self.ta = None
            else:
                self.wr(ea, v)
                if tr: self.tm[ea] = None
        elif mn == "bit":
            v = self.rd(ea)
            self.z = 1 if (self.a & v) == 0 else 0
            self.n, self.v = (v >> 7) & 1, (v >> 6) & 1
        elif mn == "tax":
            self.x = self.nz(self.a)
            if tr: self.tx = self.ta
        elif mn == "tay":
            self.y = self.nz(self.a)
            if tr: self.ty = self.ta
        elif mn == "txa":
            self.a = self.nz(self.x)
            if tr: self.ta = self.tx
        elif mn == "tya":
            self.a = self.nz(self.y)
            if tr: self.ta = self.ty
        elif mn == "tsx":
            self.x = self.nz(self.sp)
            if tr: self.tx = None
        elif mn == "txs":
            self.sp = self.x
        elif mn == "pha":
            self.push(self.a)
            if tr: self.tm[0x100 + ((self.sp + 1) & 255)] = self.ta
        elif mn == "pla":
            self.a = self.nz(self.pull())
            if tr: self.ta = self.tm.get(0x100 + self.sp)
        elif mn == "php":
            self.push(self.getp(0x10))
        elif mn == "plp":
            self.setp(self.pull())
        elif mn == "clc":
            self.c = 0
        elif mn == "sec":
            self.c = 1
        elif mn == "cld":
            self.d = 0
        elif mn == "sed":
            self.d = 1
        elif mn == "cli":
            self.i = 0
        elif mn == "sei":
            self.i = 1
        elif mn == "clv":
            self.v = 0
        elif mn == "nop":
            pass
        elif mn == "rti":
            self.setp(self.pull())
            lo = self.pull()
            self.pc = lo | (self.pull() << 8)
        else:
            raise EmuError("istruzione non supportata: %s a $%04X" % (mn, pc))

    def call(self, addr, a=0, limit=1_500_000):
        self.a, self.x, self.y = a, 0, 0
        self.sp = 0xFF
        r = SENTINEL - 1
        self.push(r >> 8)
        self.push(r & 255)
        self.pc = addr
        n = 0
        while self.pc != SENTINEL:
            self.step()
            n += 1
            if n > limit:
                raise EmuError("routine a $%04X troppo lunga o senza fine" % addr)


def sid_trace(image, load, init, play, song, frames, track=False, watch=None):
    mem = bytearray(65536)
    mem[load:load + len(image)] = image
    if track is True:
        track = (load, load + len(image))
    cpu = Cpu(mem, track or None)
    cpu.watch = watch
    cpu.call(init, song, 3_000_000)
    for f in range(frames):
        cpu.frame = f + 1
        cpu.call(play, 0, 600_000)
    return cpu


_RELOC_CACHE = {}


def trace_stable(sid, span):
    """Esegue la tune con tracciamento allungando la durata finche' l'insieme dei riferimenti trovati non
    smette di crescere (le tabelle di puntatori si scoprono man mano che la musica avanza)."""
    prev = None
    for fr in (3000, 6000, 12000, 24000):
        ref = sid_trace(sid["data"], sid["load"], sid["init"], sid["play"], sid["song"], fr, track=span)
        if prev is not None and ref.sites == prev:
            return ref, fr
        prev = set(ref.sites)
    return ref, fr


def relocate_sid(sid, new_load):
    """Sposta il SID (file + memoria di lavoro) a new_load, a pagine intere. Verifica che la sequenza di
    scritture sul SID resti identica e che la musica rilocata non legga ne' scriva piu' nella zona originale."""
    load, data = sid["load"], sid["data"]
    end = load + len(data)
    span = sid.get("span") or (load, end)
    dp = (new_load >> 8) - (load >> 8)
    if dp == 0:
        return sid, "gia' all'indirizzo richiesto"
    key = (hash(bytes(data)), load, sid["init"], sid["play"], sid["song"], new_load, span)
    if key in _RELOC_CACHE:
        return _RELOC_CACHE[key]

    def done(res):
        _RELOC_CACHE[key] = res
        return res

    new_span = (span[0] + dp * 256, span[1] + dp * 256)
    try:
        ref, frames = trace_stable(sid, span)
        if not ref.sidw:
            return done((None, "la traccia non scrive sul SID: impossibile verificare la rilocazione"))
        img = bytearray(data)
        for a in ref.sites:
            if load <= a < end:
                img[a - load] = (img[a - load] + dp) & 255
        nl = load + dp * 256
        chk = sid_trace(bytes(img), nl, sid["init"] + dp * 256, sid["play"] + dp * 256, sid["song"], frames,
                        watch=(span[0], span[1], new_span[0], new_span[1]))
    except EmuError as e:
        return done((None, "analisi non riuscita: %s" % e))
    if chk.hits:
        return done((None, "la musica rilocata usa ancora la zona originale (%s): riferimenti che non si "
                           "possono spostare in modo automatico" % hx(min(chk.hits))))
    if chk.sidw != ref.sidw:
        n = next((i for i, (p, q) in enumerate(zip(ref.sidw, chk.sidw)) if p != q), min(len(ref.sidw), len(chk.sidw)))
        return done((None, "la tune non e' rilocabile in modo automatico (la musica rilocata differisce alla "
                           "scrittura SID n. %d)" % n))
    new = dict(sid, load=nl, data=bytes(img), init=sid["init"] + dp * 256, play=sid["play"] + dp * 256,
               span=new_span)
    return done((new, "rilocato da %s a %s, verificato su %d frame (%d s di musica, %d riferimenti corretti)"
                 % (hx(load), hx(nl), frames, frames // 50, len([a for a in ref.sites if load <= a < end]))))


_PROF_CACHE = {}


def sid_profile(sid, frames=None):
    """Esegue la tune e raccoglie zero page usata e memoria scritta. None se l'analisi non riesce."""
    frames = frames or SID_FRAMES
    load, data = sid["load"], sid["data"]
    key = (hash(bytes(data)), load, sid["init"], sid["play"], sid["song"], frames)
    if key in _PROF_CACHE:
        return _PROF_CACHE[key]
    try:
        cpu = sid_trace(data, load, sid["init"], sid["play"], sid["song"], frames)
    except EmuError:
        _PROF_CACHE[key] = None
        return None
    end = load + len(data)
    clusters = []
    for a in sorted(cpu.wset):
        if clusters and a - clusters[-1][1] <= 0x100:
            clusters[-1][1] = a + 1
        else:
            clusters.append([a, a + 1])
    lo, hi, fixed = load, end, []
    for a, b in clusters:
        if b > load - 0x1000 and a < end + 0x1000:
            lo, hi = min(lo, a), max(hi, b)
        else:
            fixed.append((a, b))
    prof = dict(zp=cpu.zp, span=(lo, hi), fixed=fixed)
    _PROF_CACHE[key] = prof
    return prof


def attach_profile(sid):
    p = sid_profile(sid)
    end = sid["load"] + len(sid["data"])
    if p is None:
        return dict(sid, span=(sid["load"], end), fixed=[], zp=None, profiled=False)
    return dict(sid, span=p["span"], fixed=p["fixed"], zp=p["zp"], profiled=True)


def ideal_sid_start(sid, prg, loader_room=2200):
    """Nuovo indirizzo di caricamento ideale per il SID: l'area (file + memoria di lavoro) il piu' in alto
    possibile sotto $D000, stessa posizione nella pagina, senza toccare PRG, schermo e aree fisse."""
    slo, shi = sid.get("span") or (sid["load"], sid["load"] + len(sid["data"]))
    size = shi - slo
    top = 0xD000 - size
    start = (top & 0xFF00) | (slo & 0xFF)
    if start > top:
        start -= 0x100
    fixed = list(sid.get("fixed") or [])
    while start >= 0x0800:
        end = start + size
        blocked = [(0x0400, 0x0800)] + ([prg] if prg else []) + fixed
        if not any(overlap(start, end, p, q) for p, q in blocked):
            used = [(start, end), (0xA000, 0xC000)] + ([prg] if prg else []) + fixed
            if any(b - a >= loader_room for a, b in free_windows(used)):
                return sid["load"] + (start - slo)
        start -= 0x100
    return None


def suggest_sid_reloc(o):
    """Proposta per il pulsante 'Proponi': (indirizzo | None, messaggio)."""
    if not o.sid or not os.path.isfile(o.sid):
        return None, "Seleziona prima un file SID."
    try:
        sid = read_psid(o.sid, o.song or None)
    except (ValueError, OSError, struct.error) as e:
        return None, "SID non valido: %s" % e
    sid = attach_profile(sid)
    R = Report()
    r = check_prg(R, o) if o.prg else None
    prg = (r[0], r[0] + len(r[1])) if r else None
    s0, s1 = sid["span"]
    if any(overlap(a, b, *prg) for a, b in sid["fixed"]) if prg else False:
        return None, "La tune usa memoria fissa che il PRG sovrascrive: non si risolve spostando il SID."
    if not (s0 < 0x0800 or s1 > 0xD000 or overlap(s0, s1, 0x0400, 0x0800) or (prg and overlap(s0, s1, *prg))):
        return sid["load"], "Nessuna rilocazione necessaria: il SID (%s-%s) non crea conflitti." % (hx(s0), hx(s1 - 1))
    cand = ideal_sid_start(sid, prg)
    if cand is None:
        return None, "Non c'e' nessuna zona libera abbastanza grande per il SID (%d byte)." % (s1 - s0)
    new, msg = relocate_sid(sid, cand)
    if new is None:
        return None, "Indirizzo ideale %s, ma la tune non e' rilocabile: %s." % (hx(cand), msg)
    return cand, "Indirizzo ideale %s: %s." % (hx(cand), msg)


def analyze(o):
    """Controlla tutto e, se possibile, costruisce il .tap in memoria.
    Restituisce (Report, plan). plan["tap"] contiene i byte del .tap se non ci sono errori sugli ingressi."""
    R = Report()
    plan = dict(tap=None, regions=[], base=None, chunk=None, seconds=None)
    used = []          # (start, end, etichetta, tipo)

    # ---- parametri di base
    music = getattr(o, "music", None) or ("sid" if o.sid else "default")
    if music not in ("sid", "default", "none"):
        R.add("ERR", "Modo musica non valido: %r." % (music,))
        music = "default"
    if music == "sid" and not o.sid:
        R.add("ERR", "Hai scelto la musica da file SID: seleziona un file .sid.")
    speed = o.speed if o.speed in SPEEDS else None
    if speed is None:
        R.add("ERR", "Velocita' non valida: %r." % (o.speed,))
    try:
        chunk = int(o.chunk)
    except (TypeError, ValueError):
        chunk = -1
    if not 16 <= chunk <= 256:
        R.add("ERR", "Dimensione blocco %r non valida (16-256)." % (o.chunk,))
    for key, lo, label in (("hdr_leader", 500, "pilota header KERNAL"), ("data_leader", 200, "pilota dati KERNAL"),
                           ("first_pilot", 64, "pilota iniziale turbo"), ("chunk_pilot", MIN_PILOT + 8, "pilota tra blocchi"),
                           ("pause", 100_000, "pausa dopo il bootstrap")):
        try:
            v = int(getattr(o, key))
            if v < lo or v > 0xFFFFFF:
                raise ValueError
        except (TypeError, ValueError):
            R.add("ERR", "%s non valido (minimo %d)." % (label, lo))
    name = (o.name or "LOADER")
    if len(name) > 16:
        R.add("WARN", "Il nome del file KERNAL sara' troncato a 16 caratteri.")
    raw = raw_desc_lines(o.subtitle)
    if len(raw) > DESC_LINES:
        R.add("WARN", "La descrizione ha %d righe: verranno usate solo le prime %d." % (len(raw), DESC_LINES))
    elif len(raw) == 1 and len(wrap_desc(raw[0])) > DESC_LINES:
        R.add("WARN", "Descrizione troppo lunga (max %d caratteri): il testo in eccesso sara' tagliato." % SCROLL_MAX)
    if len(raw) > 1 and any(len(p) > DESC_WIDTH for p in raw):
        R.add("WARN", "Alcune righe della descrizione superano %d caratteri: saranno troncate." % DESC_WIDTH)
    for label, txt, mx in (("Titolo", o.title, 38), ("Descrizione", " ".join(raw), 10 ** 6)):
        if len(txt) > mx:
            R.add("WARN", "%s piu' lunga di %d caratteri: sara' troncata." % (label, mx))
        bad = sorted({c for c in txt if not (c == "@" or "A" <= c <= "Z" or "a" <= c <= "z" or " " <= c <= "?")})
        if bad:
            R.add("WARN", "%s: caratteri non disponibili sullo schermo C64 (%s): diventeranno spazi."
                  % (label, "".join(bad)))
    if not o.title.strip():
        R.add("WARN", "Titolo vuoto: la schermata mostrera' solo barra e musica.")

    righe = desc_lines(o.subtitle)
    if len(righe) > 1:
        R.add("INFO", "La descrizione ha %d righe: saranno mostrate una alla volta (circa 5 secondi ciascuna), "
                      "in loop." % len(righe))
    # ---- PRG
    r = check_prg(R, o)
    la = data = None
    run_mode = run_addr = None
    if r:
        la, data = r
        gend = la + len(data)
        used.append((la, gend, "PRG", "game"))
        sysaddr = parse_sys(la, data)
        if o.run is not None:
            if not 0 <= o.run <= 0xFFFF:
                R.add("ERR", "Indirizzo di avvio non valido.")
            else:
                run_mode, run_addr = "sys", o.run
                R.add("INFO", "Avvio forzato con JMP %s." % hx(o.run))
        elif sysaddr is not None:
            run_mode, run_addr = "sys", sysaddr
            R.add("INFO", "Avvio automatico: SYS %s (dal programma BASIC del PRG)." % hx(sysaddr))
        elif la == 0x0801:
            run_mode, run_addr = "basic", 0
            R.add("INFO", "PRG BASIC senza SYS: verra' eseguito con RUN.")
        else:
            run_mode, run_addr = "sys", la
            R.add("INFO", "PRG in linguaggio macchina: avvio a %s (indirizzo di caricamento). "
                          "Se parte da un altro punto, indica l'indirizzo di avvio." % hx(la))
        if run_mode == "sys" and not (la <= run_addr < gend) and run_addr:
            R.add("WARN", "L'indirizzo di avvio %s e' fuori dal PRG (%s-%s)." % (hx(run_addr), hx(la), hx(gend - 1)))
        if la == 0x0801 and data[:2] != bytes([0x0B, 0x08]) and sysaddr is None and len(data) > 8 and data[4] != 0x9E:
            R.add("INFO", "Il PRG non inizia con uno stub 'SYS': se e' codice puro indica l'indirizzo di avvio.")

    # ---- SID
    sid = None
    zb = 0xE0
    if music == "sid" and o.sid:
        if not os.path.isfile(o.sid):
            R.add("ERR", "Il file SID non esiste: " + o.sid)
        else:
            try:
                sid = read_psid(o.sid, o.song or None)
            except (ValueError, OSError, struct.error) as e:
                R.add("ERR", "SID: %s" % e)
        if sid:
            sid = attach_profile(sid)
            f0, f1 = sid["load"], sid["load"] + len(sid["data"])
            R.add("INFO", "SID: %s-%s, traccia %d di %d, init %s, play %s."
                  % (hx(f0), hx(f1 - 1), sid["song"] + 1, sid["songs"], hx(sid["init"]), hx(sid["play"])))
            if not sid["profiled"]:
                R.add("WARN", "Non sono riuscito a eseguire la tune per analizzarla: memoria di lavoro e zero "
                              "page non verificabili, la musica potrebbe interrompersi durante il caricamento.")
            elif sid["span"] != (f0, f1):
                R.add("INFO", "La tune usa anche memoria di lavoro fuori dal file: area complessiva %s-%s."
                      % (hx(sid["span"][0]), hx(sid["span"][1] - 1)))
            prg_rng = (la, la + len(data)) if la is not None else None

            def problem(sp):
                a0, a1 = sp
                if a0 < 0x0800 or a1 > 0xD000:
                    return "deve stare tra $0800 e $CFFF"
                if overlap(a0, a1, 0x0400, 0x0800):
                    return "copre lo schermo $0400-$07FF"
                if prg_rng and overlap(a0, a1, *prg_rng):
                    return "si sovrappone al PRG (%s-%s) e verrebbe cancellato durante il caricamento" % (
                        hx(prg_rng[0]), hx(prg_rng[1] - 1))
                return None

            for fa, fb in sid["fixed"]:
                if prg_rng and overlap(fa, fb, *prg_rng):
                    R.add("ERR", "La tune scrive in %s-%s, zona che il PRG sovrascrive: la musica si "
                                 "interromperebbe. Non si risolve spostando il SID." % (hx(fa), hx(fb - 1)))
                    sid = None
                    break
        if sid:
            mode = getattr(o, "sid_reloc", "auto")
            prob = problem(sid["span"])
            target = None
            if isinstance(mode, int):
                if not 0 <= mode <= 0xFFFF:
                    R.add("ERR", "Indirizzo di rilocazione del SID non valido.")
                    sid = None
                else:
                    target = (mode & 0xFF00) | (sid["load"] & 0xFF)
                    if (mode & 0xFF) != (sid["load"] & 0xFF):
                        R.add("WARN", "La rilocazione avviene a pagine intere: il SID andra' a %s." % hx(target))
            elif mode == "auto" and prob:
                target = ideal_sid_start(sid, prg_rng)
                if target is None:
                    R.add("ERR", "Il SID %s e nessuna zona libera e' abbastanza grande per rilocarlo." % prob)
                    sid = None
            if sid and target is not None and target != sid["load"]:
                new, msg = relocate_sid(sid, target)
                if new is None:
                    R.add("ERR", "Rilocazione del SID impossibile: %s. Usa un SID gia' rilocato (es. con "
                                 "sidreloc) oppure la musica interna." % msg)
                    sid = None
                else:
                    R.add("INFO", "SID %s." % msg)
                    sid = new
            if sid:
                prob = problem(sid["span"])
                if prob:
                    hint = {"none": " Scegli la rilocazione Automatica o Manuale.",
                            "auto": ""}.get(mode, " Cambia l'indirizzo manuale (usa 'Proponi').")
                    R.add("ERR", "Il SID (%s-%s) %s.%s" % (hx(sid["span"][0]), hx(sid["span"][1] - 1), prob, hint))
                    sid = None
        if sid:
            s0, s1 = sid["span"]
            used.append((s0, s1, "SID", "sid"))
            for fa, fb in sid["fixed"]:
                used.append((fa, fb, "SID", "sid"))
            if not (sid["load"] <= sid["init"] < sid["load"] + len(sid["data"])
                    and sid["load"] <= sid["play"] < sid["load"] + len(sid["data"])):
                R.add("WARN", "Gli indirizzi init/play non cadono dentro i dati del SID.")
            if sid["cia"]:
                R.add("WARN", "Questa traccia e' pensata per un timer CIA: il loader la suona a 50/60 Hz "
                              "(sincronizzata al video), il tempo potrebbe risultare diverso.")
            zp = sid["zp"]
            if zp is not None:
                for cand in (0xE0, 0xC0, 0xA0, 0x90):
                    if not any(cand <= a < cand + 0x20 for a in zp):
                        zb = cand
                        break
                else:
                    zb = None
                    R.add("ERR", "Il SID usa la zero page in modo troppo esteso: il loader non trova 32 byte liberi.")
                    sid = None
                    used = [u for u in used if u[3] != "sid"]
                if zb is not None and zb != 0xE0:
                    R.add("INFO", "Il SID usa la zero page $E0-$FF: variabili del loader spostate a %s-%s."
                          % (hx(zb), hx(zb + 0x1F)))
    plan["zb"] = zb

    # ---- piano di memoria, assemblaggio, tap
    input_ok = R.ok and r is not None and speed is not None and 16 <= chunk <= 256
    if input_ok:
        forbid = [(s, e) for s, e, _, _ in used]
        base_syms = {"PTHR": (SPEEDS[speed][1] + SPEEDS[speed][2]) // 2,
                     "BTHR": (SPEEDS[speed][0] + SPEEDS[speed][1]) // 2,
                     "MINP": MIN_PILOT, "MARK": MARK, "END_ADDR": la + len(data),
                     "RUN_ADDR": run_addr or 0, "ZB": zb or 0xE0, "NTOT": 0}
        if sid:
            base_syms.update(SID_INIT=sid["init"], SID_PLAY=sid["play"], SID_SONG=sid["song"])
        cfg = dict(title=o.title, subtitle=o.subtitle, music=music if music != "sid" or sid else "default",
                   run_mode=run_mode,
                   bar_tab=[0] * 256, pct_tab=[0] * 256)

        def assemble(base):
            a = Assembler(dict(base_syms, BASE=base))
            a.run(CORE_SRC + "\n" + stage2_source(cfg))
            return a

        probe = assemble(0xC000)
        size = len(probe.segs[0][1])
        s2len = probe.sym["s2_end"] - probe.sym["s2_start"]

        def base_ok(c):
            if c < 0x0800 or c + size > 0xD000:
                return "fuori dalla RAM utilizzabile ($0800-$CFFF)"
            if overlap(c, c + size, 0xA000, 0xC000):
                return "dentro $A000-$BFFF (la ROM BASIC riapparirebbe durante l'avvio)"
            if overlap(c, c + size, 0x0400, 0x0800):
                return "sopra lo schermo $0400-$07FF"
            for s, e in forbid:
                if overlap(c, c + size, s, e):
                    return "in conflitto con %s-%s" % (hx(s), hx(e - 1))
            return None

        cands = list(range(0xC000, 0xD000 - size + 1, 0x100)) + list(range(0x9F00 - size, 0x07FF, -0x100))
        auto = next((c for c in cands if base_ok(c) is None), None)
        base = None
        if o.loader_addr is not None:
            if not 0 <= o.loader_addr <= 0xFFFF:
                R.add("ERR", "Indirizzo del loader non valido.")
            else:
                why = base_ok(o.loader_addr)
                if why:
                    R.add("ERR", "Il loader (%d byte) a %s non puo' stare: %s. %s" % (
                        size, hx(o.loader_addr), why,
                        ("Indirizzo automatico consigliato: %s." % hx(auto)) if auto else "Nessuna zona libera."))
                else:
                    base = o.loader_addr
                    R.add("INFO", "Loader a %s (scelto a mano), %d byte." % (hx(base), size))
        else:
            if auto is None:
                R.add("ERR", "Nessuna zona libera di %d byte per il loader. Zone libere: %s."
                      % (size, fmt_windows(free_windows(forbid))))
            else:
                base = auto
                R.add("INFO", "Loader a %s (scelto automaticamente), %d byte." % (hx(base), size))
                if base != 0xC000:
                    R.add("INFO", "$C000 era occupato: il loader e' stato spostato.")
        if base is not None:
            used.append((base, base + size, "Loader", "loader"))
            n_sid = -(-len(sid["data"]) // chunk) if sid else 0
            req = chunk
            while True:
                n_g = -(-len(data) // chunk)
                n_s = -(-(len(sid["data"])) // chunk) if sid else 0
                n_s2 = -(-s2len // chunk)
                n_pre, n_tot = n_s2 + 1 + n_s, n_s2 + 1 + n_s + n_g
                if n_tot <= 255 or chunk >= 256:
                    break
                chunk = min(256, chunk + 16)
            if n_tot > 255:
                R.add("ERR", "Troppi blocchi (%d, max 255): il PRG e' troppo grande per questo loader." % n_tot)
            else:
                if chunk != req:
                    R.add("WARN", "Dimensione blocco portata da %d a %d per restare entro 255 blocchi." % (req, chunk))
                base_syms["NTOT"] = n_tot
                bar, pct = [], []
                for i in range(256):
                    g = min(max(i - n_pre, 0), n_g)
                    bar.append(g * 32 // n_g)
                    pct.append(g * 100 // n_g)
                cfg["bar_tab"], cfg["pct_tab"] = bar, pct
                asm = assemble(base)
                mem = bytes(asm.segs[0][1])
                s2s, s2e, ce = asm.sym["s2_start"], asm.sym["s2_end"], asm.sym["core_end"]
                core_img = mem[:ce - base]
                s2chunks = split_chunks(s2s, mem[s2s - base:s2e - base], chunk)
                sidchunks = split_chunks(sid["load"], sid["data"], chunk) if sid else []
                gchunks = split_chunks(la, data, chunk)
                assert len(s2chunks) + 1 + len(sidchunks) == n_pre
                npages = (len(core_img) + 255) // 256
                a1 = Assembler({"BASE": base, "NPAGES": npages})
                a1.run(STAGE1_SRC)
                st1 = bytes(a1.segs[0][1]) + core_img + b"\x00" * (npages * 256 - len(core_img))
                tap = Tap()
                kernal_program(tap, name, 0x0801, st1, int(o.hdr_leader), int(o.data_leader))
                t_boot = tap.total
                tap.pause(int(o.pause))
                state = {"first": True}

                def emit(addr, d, flags):
                    turbo_chunk(tap, speed, addr, d, flags,
                                int(o.first_pilot) if state["first"] else int(o.chunk_pilot))
                    state["first"] = False

                for a, d in s2chunks:
                    emit(a, d, 0)
                emit(asm.sym["s2_stub"], bytes([0x4C, asm.sym["s2_main"] & 255, asm.sym["s2_main"] >> 8]), 1)
                for i, (a, d) in enumerate(sidchunks):
                    emit(a, d, 2 if i == len(sidchunks) - 1 else 0)
                for i, (a, d) in enumerate(gchunks):
                    emit(a, d, 0x80 if i == len(gchunks) - 1 else 0)
                tap.pulses([SPEEDS[speed][2]] * 24)
                sec = lambda c: c / PAL_CLOCK
                plan.update(sym=dict(asm.sym), tap=tap.tobytes(), base=base, chunk=chunk, size=size, st1=len(st1),
                            seconds=sec(tap.total), boot_seconds=sec(t_boot), n_game=len(gchunks),
                            n_tot=n_tot, run_mode=run_mode, run_addr=run_addr)
                R.add("INFO", "Blocchi turbo: %d (di cui %d del gioco), %d byte ciascuno." % (n_tot, len(gchunks), chunk))
                tot, bt = int(round(sec(tap.total))), int(round(sec(t_boot)))
                R.add("INFO", "Durata stimata (PAL): bootstrap ~%d s + turbo ~%d s, totale %d:%02d."
                      % (bt, tot - bt, tot // 60, tot % 60))
                if speed == "fast":
                    R.add("WARN", "Velocita' 'fast': pensata solo per emulatori, su datassette vero e' rischiosa.")
                if speed == "slow" and sec(tap.total) > 600:
                    R.add("INFO", "Caricamento lungo: valuta la velocita' 'normal' se il datassette e' buono.")
    # ---- destinazione
    if not o.output:
        R.add("ERR", "Scegli il file .tap di destinazione.")
    else:
        d = os.path.dirname(os.path.abspath(o.output))
        if not os.path.isdir(d):
            R.add("ERR", "La cartella di destinazione non esiste: " + d)
        elif not os.access(d, os.W_OK):
            R.add("ERR", "Cartella di destinazione non scrivibile: " + d)
        elif os.path.isdir(o.output):
            R.add("ERR", "La destinazione e' una cartella: indica un nome di file.")
        else:
            if os.path.exists(o.output):
                R.add("WARN", "Il file di destinazione esiste e verra' sovrascritto.")
            if r and os.path.abspath(o.output) == os.path.abspath(o.prg):
                R.add("ERR", "La destinazione coincide con il PRG di origine!")
            if not o.output.lower().endswith(".tap"):
                R.add("WARN", "La destinazione non termina con .tap.")
    plan["regions"] = used
    return R, plan


def write_tap(o, plan):
    with open(o.output, "wb") as f:
        f.write(plan["tap"])


# ---------------------------------------------------------------------------
# Riga di comando
# ---------------------------------------------------------------------------
def cli(argv):
    ap = argparse.ArgumentParser(
        description="Crea un .tap per Commodore 64 con turbo loader, grafica, musica SID e il tuo PRG. "
                    "Senza argomenti apre l'interfaccia grafica.")
    ap.add_argument("--version", action="version", version="C64 TAP Builder %s" % __version__)
    ap.add_argument("prg", nargs="?", help="PRG del gioco")
    ap.add_argument("-o", "--output", help="file .tap di uscita (default: nome del PRG + .tap)")
    ap.add_argument("--gui", action="store_true", help="apri l'interfaccia grafica")
    ap.add_argument("--check", action="store_true", help="esegui solo i controlli, senza scrivere il .tap")
    ap.add_argument("--preset", choices=list(PRESETS), help="; ".join("%s = %s" % (k, v[0]) for k, v in PRESETS.items()))
    ap.add_argument("--name", help="nome del primo file (max 16 car.)")
    ap.add_argument("--title", help="titolo mostrato dal loader (max 38 car.)")
    ap.add_argument("--subtitle", help="descrizione in basso (max 10 righe da 38 caratteri): separa le righe "
                                       "con '|'; una sola frase lunga viene spezzata da sola")
    ap.add_argument("--sid", help="file .sid (PSID); default: musica interna")
    ap.add_argument("--music", choices=["sid", "default", "none"],
                    help="musica di caricamento: sid (file .sid), default (interna) o none (nessuna); "
                         "se manca e c'e' --sid, usa il SID")
    ap.add_argument("--song", type=int, help="numero traccia del SID")
    ap.add_argument("--sid-reloc", metavar="none|auto|ADDR", help="rilocazione del SID: none, auto (default: "
                    "sposta solo se c'e' un conflitto) oppure un indirizzo, es. $C800")
    ap.add_argument("--speed", choices=list(SPEEDS), help="slow/normal/fast")
    ap.add_argument("--chunk", type=int, help="byte per blocco turbo (16-256)")
    ap.add_argument("--run", type=lambda x: parse_addr(x), help="indirizzo di avvio (default: SYS del PRG)")
    ap.add_argument("--loader-addr", type=lambda x: parse_addr(x), help="indirizzo del loader (default: automatico)")
    for k in ("hdr_leader", "data_leader", "pause", "first_pilot", "chunk_pilot"):
        ap.add_argument("--" + k.replace("_", "-"), type=int, dest=k, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.gui:
        return run_gui(a.prg)
    kw = {}
    if a.preset:
        kw.update(PRESETS[a.preset][1])
    if a.sid_reloc:
        v = a.sid_reloc.strip().lower()
        try:
            kw["sid_reloc"] = v if v in ("none", "auto") else parse_addr(v)
        except ValueError:
            ap.error("--sid-reloc: usa none, auto o un indirizzo")
    if a.music:
        kw["music"] = a.music
    for k in ("name", "title", "subtitle", "sid", "song", "speed", "chunk", "run", "loader_addr",
              "hdr_leader", "data_leader", "pause", "first_pilot", "chunk_pilot"):
        if getattr(a, k) is not None:
            kw[k] = getattr(a, k)
    o = make_opts(prg=a.prg or "", output=a.output or (os.path.splitext(a.prg)[0] + ".tap" if a.prg else ""), **kw)
    R, plan = analyze(o)
    print(R.text())
    if not R.ok:
        print("\nNon posso generare il file: correggi gli errori sopra.")
        return 1
    if a.check:
        return 0
    write_tap(o, plan)
    print("\nCreato %s (%d byte)" % (o.output, len(plan["tap"])))
    return 0


# ---------------------------------------------------------------------------
# Interfaccia grafica
# ---------------------------------------------------------------------------
CONF_PATH = os.path.join(os.path.expanduser("~"), ".config", "c64tap_gui.json")


def run_gui(initial_prg=None, initial_sid=None):
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except ImportError:
        raise SystemExit("tkinter non e' installato. Su Debian/Ubuntu: sudo apt install python3-tk")

    root = tk.Tk()
    root.title("C64 TAP Builder %s - turbo loader" % __version__)
    root.minsize(1000, 600)
    try:
        conf = json.load(open(CONF_PATH))
    except (OSError, ValueError):
        conf = {}

    V = {k: tk.StringVar() for k in ("prg", "sid", "sid_addr", "output", "name", "title", "subtitle", "speed", "chunk",
                                     "song", "loader_addr", "run", "hdr_leader", "data_leader", "pause",
                                     "first_pilot", "chunk_pilot")}
    loader_auto = tk.BooleanVar(value=True)
    reloc_mode = tk.StringVar(value="Automatica (solo se serve)")
    music_var = tk.StringVar(value="default")
    run_auto = tk.BooleanVar(value=True)
    preset_var = tk.StringVar()
    state = {"job": None, "applying": False, "plan": None, "last_out": ""}

    def setdefaults():
        for k, v in V.items():
            val = DEFAULTS.get(k)
            v.set("" if val is None else str(val))
        V["song"].set("0")

    setdefaults()
    for k in ("name", "title"):
        if k in conf:
            V[k].set(conf[k])
    if conf.get("music") in ("sid", "default", "none"):
        music_var.set(conf["music"])
    preset_names = {v[0]: k for k, v in PRESETS.items()}

    def apply_preset(key):
        state["applying"] = True
        for k, val in PRESETS[key][1].items():
            V[k].set(str(val))
        state["applying"] = False

    apply_preset(conf.get("preset", "emu") if conf.get("preset") in PRESETS else "emu")
    preset_var.set(PRESETS[conf.get("preset", "emu") if conf.get("preset") in PRESETS else "emu"][0])
    if initial_prg:
        V["prg"].set(initial_prg)
    if initial_sid:
        V["sid"].set(initial_sid)
        music_var.set("sid")

    pad = dict(padx=6, pady=3)
    main = ttk.Frame(root, padding=6)
    main.pack(fill="both", expand=True)
    main.columnconfigure(0, weight=5)
    main.columnconfigure(1, weight=6)
    main.rowconfigure(0, weight=1)
    left = ttk.Frame(main)
    left.grid(row=0, column=0, sticky="nsew")
    left.columnconfigure(0, weight=1)
    right = ttk.Frame(main)
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(0, weight=1)
    root.geometry("1240x660")

    def pick_open(var, title, types, key):
        d = conf.get(key) or os.path.expanduser("~")
        p = filedialog.askopenfilename(title=title, filetypes=types, initialdir=d)
        if p:
            var.set(p)
            conf[key] = os.path.dirname(p)

    def pick_save():
        d = conf.get("dir_out") or (os.path.dirname(V["prg"].get()) or os.path.expanduser("~"))
        ini = os.path.basename(V["output"].get()) or "loader.tap"
        p = filedialog.asksaveasfilename(title="Salva il file .tap", defaultextension=".tap",
                                         filetypes=[("Immagine nastro", "*.tap"), ("Tutti", "*.*")],
                                         initialdir=d, initialfile=ini)
        if p:
            V["output"].set(p)
            conf["dir_out"] = os.path.dirname(p)

    r = 0
    box = ttk.LabelFrame(left, text="File")
    box.grid(row=r, column=0, sticky="ew", **pad)
    box.columnconfigure(1, weight=1)
    ttk.Label(box, text="PRG del gioco:").grid(row=0, column=0, sticky="w", **pad)
    ttk.Entry(box, textvariable=V["prg"]).grid(row=0, column=1, sticky="ew", **pad)
    ttk.Button(box, text="Sfoglia...", command=lambda: pick_open(
        V["prg"], "Scegli il PRG", [("Programma C64", "*.prg *.PRG"), ("Tutti", "*.*")], "dir_prg")
    ).grid(row=0, column=2, **pad)
    ttk.Label(box, text="Musica di caricamento:").grid(row=1, column=0, sticky="w", **pad)
    mf = ttk.Frame(box)
    mf.grid(row=1, column=1, columnspan=2, sticky="w", **pad)
    for txt_, val_ in (("File SID", "sid"), ("Musica predefinita", "default"), ("Nessuna musica", "none")):
        ttk.Radiobutton(mf, text=txt_, value=val_, variable=music_var).pack(side="left", padx=(0, 12))
    ttk.Label(box, text="File SID:").grid(row=2, column=0, sticky="w", **pad)
    sid_entry = ttk.Entry(box, textvariable=V["sid"])
    sid_entry.grid(row=2, column=1, sticky="ew", **pad)
    sb = ttk.Frame(box)
    sb.grid(row=2, column=2, **pad)
    sid_btn = ttk.Button(sb, text="Sfoglia...", command=lambda: pick_open(
        V["sid"], "Scegli il SID", [("SID", "*.sid *.SID"), ("Tutti", "*.*")], "dir_sid"))
    sid_btn.pack(side="left")
    sid_clear = ttk.Button(sb, text="X", width=3, command=lambda: V["sid"].set(""))
    sid_clear.pack(side="left", padx=(3, 0))
    ttk.Label(box, text="Traccia SID (0 = predefinita):").grid(row=3, column=0, sticky="w", **pad)
    song_spin = ttk.Spinbox(box, from_=0, to=255, width=6, textvariable=V["song"])
    song_spin.grid(row=3, column=1, sticky="w", **pad)
    ttk.Label(box, text="Rilocazione SID:").grid(row=4, column=0, sticky="w", **pad)
    rf = ttk.Frame(box)
    rf.grid(row=4, column=1, columnspan=2, sticky="ew", **pad)
    RELOC_LABELS = ["Automatica (solo se serve)", "Nessuna", "Manuale"]
    reloc_cb = ttk.Combobox(rf, textvariable=reloc_mode, values=RELOC_LABELS, state="readonly", width=24)
    reloc_cb.pack(side="left")
    reloc_entry = ttk.Entry(rf, textvariable=V["sid_addr"], width=9)
    reloc_entry.pack(side="left", padx=6)
    reloc_btn = ttk.Button(rf, text="Proponi", command=lambda: propose_reloc())
    reloc_btn.pack(side="left")
    ttk.Label(box, text="File .tap di destinazione:").grid(row=5, column=0, sticky="w", **pad)
    ttk.Entry(box, textvariable=V["output"]).grid(row=5, column=1, sticky="ew", **pad)
    ttk.Button(box, text="Salva come...", command=pick_save).grid(row=5, column=2, **pad)

    r += 1
    pb = ttk.LabelFrame(left, text="Destinazione di riproduzione (preset)")
    pb.grid(row=r, column=0, sticky="ew", **pad)
    pb.columnconfigure(1, weight=1)
    ttk.Label(pb, text="Preset:").grid(row=0, column=0, sticky="w", **pad)
    cb = ttk.Combobox(pb, textvariable=preset_var, state="readonly",
                      values=[v[0] for v in PRESETS.values()] + [CUSTOM_PRESET])
    cb.grid(row=0, column=1, sticky="ew", **pad)
    desc = ttk.Label(pb, text="", wraplength=480, foreground="#555")
    desc.grid(row=1, column=0, columnspan=2, sticky="w", **pad)

    def on_preset(_e=None):
        key = preset_names.get(preset_var.get())
        if key:
            apply_preset(key)
            desc.config(text=PRESETS[key][2])
        else:
            desc.config(text="Parametri modificati a mano.")
        schedule()

    cb.bind("<<ComboboxSelected>>", on_preset)

    r += 1
    tb = ttk.LabelFrame(left, text="Schermata di caricamento")
    tb.grid(row=r, column=0, sticky="ew", **pad)
    tb.columnconfigure(1, weight=1)
    DV = [tk.StringVar() for _ in range(DESC_LINES)]
    desc_summary = tk.StringVar()

    def sync_desc(*_):
        lines = []
        for v in DV:
            t = v.get()
            if len(t) > DESC_WIDTH:
                t = t[:DESC_WIDTH]
                v.set(t)
            if t.strip():
                lines.append(t.strip())
        V["subtitle"].set("\n".join(lines))
        if lines:
            desc_summary.set("%d %s, %d/%d caratteri - \u00ab%s\u00bb%s" % (
                len(lines), "riga" if len(lines) == 1 else "righe", sum(len(x) for x in lines), SCROLL_MAX,
                lines[0][:22], "..." if len(lines[0]) > 22 or len(lines) > 1 else ""))
        else:
            desc_summary.set("(nessuna descrizione)")

    for v in DV:
        v.trace_add("write", sync_desc)

    def load_desc(text):
        ls = desc_lines(text)
        for i, v in enumerate(DV):
            v.set(ls[i] if i < len(ls) else "")
        sync_desc()

    def open_desc():
        w = state.get("dw")
        if w is not None and w.winfo_exists():
            w.deiconify()
            w.lift()
            w.focus_force()
            return
        w = tk.Toplevel(root)
        state["dw"] = w
        w.title("Descrizione della schermata di caricamento")
        w.transient(root)
        w.resizable(False, False)
        f = ttk.Frame(w, padding=10)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Fino a %d righe da %d caratteri (max %d in tutto). Le caselle vuote vengono ignorate: "
                          "a video compaiono solo le righe compilate, una alla volta (circa 5 secondi ciascuna), "
                          "in loop." % (DESC_LINES, DESC_WIDTH, SCROLL_MAX),
                  wraplength=520, foreground="#555").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        counters, entries = [], []
        for i, v in enumerate(DV):
            ttk.Label(f, text="Riga %d" % (i + 1)).grid(row=i + 1, column=0, sticky="w", padx=4, pady=2)
            e = ttk.Entry(f, textvariable=v, width=44)
            e.grid(row=i + 1, column=1, sticky="w", padx=4, pady=2)
            c = ttk.Label(f, width=6, anchor="e", foreground="#555")
            c.grid(row=i + 1, column=2, padx=4)
            entries.append(e)
            counters.append(c)
        total = ttk.Label(f, foreground="#555")
        total.grid(row=DESC_LINES + 1, column=0, columnspan=3, sticky="w", padx=4, pady=(6, 0))

        def upd(*_):
            n = 0
            for v, c in zip(DV, counters):
                t = len(v.get())
                n += len(v.get().strip())
                c.config(text="%d/%d" % (t, DESC_WIDTH))
            total.config(text="Totale: %d/%d caratteri" % (n, SCROLL_MAX))

        tids = [v.trace_add("write", upd) for v in DV]
        upd()

        def on_destroy(e):
            if e.widget is w:
                for v, t in zip(DV, tids):
                    try:
                        v.trace_remove("write", t)
                    except tk.TclError:
                        pass

        w.bind("<Destroy>", on_destroy)
        bt3 = ttk.Frame(f)
        bt3.grid(row=DESC_LINES + 2, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(bt3, text="Svuota tutto", command=lambda: [v.set("") for v in DV]).pack(side="left", padx=4)
        ttk.Button(bt3, text="Chiudi", command=w.destroy).pack(side="left", padx=4)
        entries[0].focus_set()
        w.update_idletasks()
        w.geometry("+%d+%d" % (root.winfo_rootx() + 80, root.winfo_rooty() + 40))

    load_desc(conf.get("subtitle", ""))
    ttk.Label(tb, text="Titolo (max 38):").grid(row=0, column=0, sticky="w", **pad)
    ttk.Entry(tb, textvariable=V["title"]).grid(row=0, column=1, columnspan=2, sticky="ew", **pad)
    ttk.Label(tb, text="Descrizione:").grid(row=1, column=0, sticky="w", **pad)
    ttk.Label(tb, textvariable=desc_summary, foreground="#333", wraplength=330).grid(
        row=1, column=1, sticky="w", **pad)
    ttk.Button(tb, text="Modifica...", command=open_desc).grid(row=1, column=2, **pad)
    ttk.Label(tb, text="In alto resta fissa la scritta \u00ab%s\u00bb." % CREDIT,
              foreground="#555", wraplength=480).grid(row=2, column=0, columnspan=3, sticky="w", **pad)
    ttk.Label(tb, text="Nome file sul nastro (max 16):").grid(row=3, column=0, sticky="w", **pad)
    ttk.Entry(tb, textvariable=V["name"]).grid(row=3, column=1, columnspan=2, sticky="ew", **pad)

    r += 1
    ab = ttk.LabelFrame(left, text="Velocita' e indirizzi")
    ab.grid(row=r, column=0, sticky="ew", **pad)
    ttk.Label(ab, text="Velocita' turbo:").grid(row=0, column=0, sticky="w", **pad)
    ttk.Combobox(ab, textvariable=V["speed"], values=list(SPEEDS), state="readonly", width=8
                 ).grid(row=0, column=1, sticky="w", **pad)
    ttk.Label(ab, text="Byte per blocco:").grid(row=0, column=2, sticky="e", **pad)
    ttk.Spinbox(ab, from_=16, to=256, increment=16, width=6, textvariable=V["chunk"]).grid(row=0, column=3, sticky="w", **pad)
    ttk.Checkbutton(ab, text="Indirizzo loader automatico", variable=loader_auto).grid(row=1, column=0, columnspan=2, sticky="w", **pad)
    le = ttk.Entry(ab, textvariable=V["loader_addr"], width=10)
    le.grid(row=1, column=2, columnspan=2, sticky="w", **pad)
    ttk.Checkbutton(ab, text="Avvio automatico (SYS del PRG)", variable=run_auto).grid(row=2, column=0, columnspan=2, sticky="w", **pad)
    re_ = ttk.Entry(ab, textvariable=V["run"], width=10)
    re_.grid(row=2, column=2, columnspan=2, sticky="w", **pad)
    ttk.Label(ab, text="(indirizzi in esadecimale, es. $C000)", foreground="#555").grid(row=3, column=0, columnspan=4, sticky="w", **pad)

    adv_win = {"w": None}

    def open_adv():
        w = adv_win["w"]
        if w is not None and w.winfo_exists():
            w.deiconify()
            w.lift()
            w.focus_force()
            return
        w = tk.Toplevel(root)
        adv_win["w"] = w
        w.title("Temporizzazioni avanzate")
        w.transient(root)
        w.resizable(False, False)
        f = ttk.Frame(w, padding=10)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Durate dei toni pilota e delle pause. I preset le impostano da soli: "
                          "modificale solo se il caricamento da datassette si blocca.",
                  wraplength=430, foreground="#555").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        rows = (("Pilota header KERNAL:", "hdr_leader", "impulsi (min. 500)"),
                ("Pilota dati KERNAL:", "data_leader", "impulsi (min. 200)"),
                ("Pausa dopo il bootstrap:", "pause", "cicli di clock (1 s = 985248)"),
                ("Pilota iniziale turbo:", "first_pilot", "impulsi (min. 64)"),
                ("Pilota tra i blocchi:", "chunk_pilot", "impulsi (min. %d)" % (MIN_PILOT + 8)))
        for i, (lab, key, hint) in enumerate(rows, start=1):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky="w", padx=4, pady=3)
            ttk.Entry(f, textvariable=V[key], width=11).grid(row=i, column=1, sticky="w", padx=4, pady=3)
            ttk.Label(f, text=hint, foreground="#555").grid(row=i, column=2, sticky="w", padx=4)
        bt2 = ttk.Frame(f)
        bt2.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="e", pady=(10, 0))

        def restore():
            key = preset_names.get(preset_var.get()) or "emu"
            apply_preset(key)
            preset_var.set(PRESETS[key][0])
            schedule()

        ttk.Button(bt2, text="Ripristina preset", command=restore).pack(side="left", padx=4)
        ttk.Button(bt2, text="Chiudi", command=w.destroy).pack(side="left", padx=4)
        w.update_idletasks()
        w.geometry("+%d+%d" % (root.winfo_rootx() + 60, root.winfo_rooty() + 80))

    ttk.Button(ab, text="Temporizzazioni avanzate...", command=open_adv
               ).grid(row=4, column=0, columnspan=4, sticky="w", **pad)
    r += 2

    mp = ttk.LabelFrame(right, text="Mappa di memoria")
    mp.grid(row=r, column=0, sticky="ew", **pad)
    cv = tk.Canvas(mp, width=400, height=92, highlightthickness=0)
    cv.pack(fill="x", padx=6, pady=4)
    legend = ttk.Label(mp, text="", wraplength=520)
    legend.pack(fill="x", padx=6)

    r += 1
    rb = ttk.LabelFrame(right, text="Controlli")
    rb.grid(row=r, column=0, sticky="nsew", **pad)
    right.rowconfigure(r, weight=1)
    txt = tk.Text(rb, height=14, width=50, wrap="word", state="disabled", font=("TkDefaultFont", 10))
    sc = ttk.Scrollbar(rb, command=txt.yview)
    txt.configure(yscrollcommand=sc.set)
    sc.pack(side="right", fill="y")
    txt.pack(fill="both", expand=True)
    txt.tag_config("ERR", foreground="#b00020")
    txt.tag_config("WARN", foreground="#a05a00")
    txt.tag_config("INFO", foreground="#222")

    r += 1
    bt = ttk.Frame(right)
    bt.grid(row=r, column=0, sticky="ew", **pad)
    status = ttk.Label(bt, text="")
    status.pack(side="left")
    gen = ttk.Button(bt, text="Genera .tap")
    gen.pack(side="right")
    ttk.Button(bt, text="Ricontrolla", command=lambda: refresh()).pack(side="right", padx=6)

    PAL = {"free": "#c8e6c9", "sys": "#6d4c41", "screen": "#d81b60", "basic": "#e57373", "game": "#1e88e5",
           "sid": "#8e24aa", "loader": "#fb8c00", "io": "#37474f"}
    LEG = (("Libera", "free"), ("Sistema", "sys"), ("Schermo loader", "screen"), ("ROM BASIC", "basic"),
           ("PRG", "game"), ("SID", "sid"), ("Loader", "loader"), ("I/O e ROM", "io"))

    def draw_map(plan):
        cv.delete("all")
        w = max(cv.winfo_width(), 400)
        sx = lambda a: 4 + a * (w - 8) / 65536.0

        def rect(a, b, key, label=None, stipple=None):
            x0, x1 = sx(a), max(sx(b), sx(a) + 2)
            cv.create_rectangle(x0, 8, x1, 36, fill=PAL[key], outline="", stipple=stipple or "")
            if label and x1 - x0 > 34:
                cv.create_text((x0 + x1) / 2, 22, text=label, fill="white", font=("TkDefaultFont", 8, "bold"))

        rect(0, 65536, "free")
        rect(0, 0x0400, "sys")
        rect(0x0400, 0x0800, "screen")
        rect(0xA000, 0xC000, "basic", stipple="gray50")
        rect(0xD000, 0x10000, "io", "I/O-ROM")
        for s_, e_, lab, kind in plan.get("regions", []):
            rect(s_, e_, kind, lab if lab != "SID (lavoro)" else "SID")
        cv.create_rectangle(sx(0), 8, sx(65536), 36, outline="#222")
        for a in (0, 0x4000, 0x8000, 0xC000, 0xFFFF):
            cv.create_text(min(max(sx(a), 18), w - 18), 47, text=hx(a), font=("TkDefaultFont", 8))
        for i, (txt_, key) in enumerate(LEG):
            x = 6 + (i % 4) * max((w - 12) // 4, 100)
            y = 64 + (i // 4) * 16
            cv.create_rectangle(x, y - 5, x + 11, y + 6, fill=PAL[key], outline="#222")
            cv.create_text(x + 16, y, text=txt_, anchor="w", font=("TkDefaultFont", 8))
        free = free_windows([(s_, e_) for s_, e_, _, _ in plan.get("regions", [])] + [(0xA000, 0xC000)])
        legend.config(text="Zone libere: " + fmt_windows(free))

    def collect():
        o = make_opts()
        for k in ("prg", "sid", "output", "name", "title", "subtitle", "speed"):
            setattr(o, k, V[k].get().strip() if k not in ("title", "subtitle") else V[k].get())
        def num(k, dflt=-1):
            try:
                return int(V[k].get())
            except ValueError:
                return dflt
        for k in ("chunk", "hdr_leader", "data_leader", "pause", "first_pilot", "chunk_pilot"):
            setattr(o, k, num(k))
        o.song = max(num("song", 0), 0)
        o.music = music_var.get()
        mode = reloc_mode.get()
        if mode.startswith("Nessuna"):
            o.sid_reloc = "none"
        elif mode.startswith("Manuale"):
            try:
                o.sid_reloc = parse_addr(V["sid_addr"].get())
            except ValueError:
                o.sid_reloc = -1
        else:
            o.sid_reloc = "auto"
        o.loader_addr = o.run = None
        if not loader_auto.get():
            try:
                o.loader_addr = parse_addr(V["loader_addr"].get())
            except ValueError:
                o.loader_addr = -1
        if not run_auto.get():
            try:
                o.run = parse_addr(V["run"].get())
            except ValueError:
                o.run = -1
        return o

    def refresh():
        state["job"] = None
        o = collect()
        use_sid = music_var.get() == "sid"
        for w_ in (sid_entry, sid_btn, sid_clear, song_spin, reloc_cb, reloc_btn):
            w_.state(["!disabled" if use_sid else "disabled"])
        reloc_entry.state(["!disabled" if use_sid and reloc_mode.get().startswith("Manuale") else "disabled"])
        le.state(["!disabled" if not loader_auto.get() else "disabled"])
        re_.state(["!disabled" if not run_auto.get() else "disabled"])
        if o.music == "sid" and o.sid:
            status.config(text="Analisi del SID in corso...", foreground="#555")
            root.update_idletasks()
        R, plan = analyze(o)
        state["plan"], state["o"], state["R"] = plan, o, R
        txt.config(state="normal")
        txt.delete("1.0", "end")
        order = {"ERR": 0, "WARN": 1, "INFO": 2}
        for lvl, msg in sorted(R.items, key=lambda x: order[x[0]]):
            mark = {"ERR": "\u2716 ", "WARN": "\u26a0 ", "INFO": "\u2022 "}[lvl]
            txt.insert("end", mark + msg + "\n", lvl)
        txt.config(state="disabled")
        n_err = sum(1 for l, _ in R.items if l == "ERR")
        n_w = sum(1 for l, _ in R.items if l == "WARN")
        status.config(text=("Pronto" if R.ok else "%d %s" % (n_err, "errore" if n_err == 1 else "errori")) + (", %d %s" % (n_w, "avviso" if n_w == 1 else "avvisi") if n_w else ""),
                      foreground="#0a7a0a" if R.ok else "#b00020")
        gen.state(["!disabled"] if R.ok else ["disabled"])
        draw_map(plan)

    def propose_reloc():
        o = collect()
        if o.music != "sid":
            messagebox.showwarning("Rilocazione SID", "Scegli prima 'File SID' come musica di caricamento.")
            return
        status.config(text="Calcolo dell'indirizzo ideale...", foreground="#555")
        root.update_idletasks()
        addr, msg = suggest_sid_reloc(o)
        if addr is None:
            messagebox.showwarning("Rilocazione SID", msg)
        else:
            V["sid_addr"].set(hx(addr))
            reloc_mode.set("Manuale")
            messagebox.showinfo("Rilocazione SID", msg)
        refresh()

    def schedule(*_):
        if state["applying"]:
            return
        if state["job"]:
            root.after_cancel(state["job"])
        state["job"] = root.after(250, refresh)

    def manual_change(*_):
        if not state["applying"] and preset_names.get(preset_var.get()):
            preset_var.set(CUSTOM_PRESET)
            desc.config(text="Parametri modificati a mano.")
        schedule()

    for k in TAPE_KEYS:
        V[k].trace_add("write", manual_change)
    for k in ("prg", "sid", "output", "name", "title", "subtitle", "song", "loader_addr", "run"):
        V[k].trace_add("write", schedule)
    loader_auto.trace_add("write", schedule)
    reloc_mode.trace_add("write", schedule)
    music_var.trace_add("write", schedule)
    V["sid_addr"].trace_add("write", schedule)
    run_auto.trace_add("write", schedule)

    def auto_output(*_):
        p = V["prg"].get().strip()
        cur = V["output"].get().strip()
        if p and (not cur or cur == state["last_out"]):
            new = os.path.splitext(p)[0] + ".tap"
            state["last_out"] = new
            V["output"].set(new)

    V["prg"].trace_add("write", auto_output)
    auto_output()

    def generate():
        refresh()
        R, plan, o = state["R"], state["plan"], state["o"]
        if not R.ok:
            return
        warns = [m for l, m in R.items if l == "WARN"]
        if warns and not messagebox.askyesno("Avvisi", "Ci sono %d avvisi:\n\n- %s\n\nGenerare comunque?" % (
                len(warns), "\n- ".join(warns[:6]))):
            return
        try:
            write_tap(o, plan)
        except OSError as e:
            messagebox.showerror("Errore", "Impossibile scrivere il file:\n%s" % e)
            return
        save_conf()
        messagebox.showinfo("Fatto", "Creato %s\n%d byte, durata stimata %d:%02d" % (
            o.output, len(plan["tap"]), plan["seconds"] // 60, plan["seconds"] % 60))

    gen.config(command=generate)

    def save_conf():
        conf.update(name=V["name"].get(), title=V["title"].get(), subtitle=V["subtitle"].get(),
                    music=music_var.get(),
                    preset=preset_names.get(preset_var.get(), conf.get("preset", "emu")))
        try:
            os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
            json.dump(conf, open(CONF_PATH, "w"))
        except OSError:
            pass

    def on_close():
        save_conf()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    key0 = preset_names.get(preset_var.get())
    desc.config(text=PRESETS[key0][2] if key0 else "")
    cv.bind("<Configure>", lambda e: refresh())
    root.after(100, refresh)
    root.mainloop()
    return 0


def main():
    if len(sys.argv) == 1:
        return run_gui()
    return cli(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
