# C64 TAP Builder

**Build a Commodore 64 `.tap` tape image with a turbo loader, an animated loading screen, SID music and your own program.**

*[Versione italiana](README.md)*

![Graphical interface](docs/gui.png)

Give C64 TAP Builder a `.prg` file (your game or program) and get back a `.tap` tape image that loads much faster than
a standard tape, showing a loading screen with a rainbow title, a progress bar, a paged text message and music.
It works from a graphical interface or from the command line. The interface text is in Italian.

## Features

- **Interrupt-driven 6502 turbo loader** (CIA1 FLAG pin): the CPU stays free for music and graphics while data arrives.
  Every block carries its own checksum.
- **Loading screen**: animated rainbow title, progress bar with percentage, border stripes synchronised with the
  incoming data, a fixed credit line and up to 10 description lines (38 characters each) shown one at a time.
- **Music of your choice**: a `.sid` file (PSID), the built-in default tune, or no music.
- **Automatic SID relocation**: if the tune overlaps your program it is moved to a free area and the result is checked
  with a built-in 6502 emulator. A button proposes the ideal address.
- **Checks before building**: detects wrong inputs (D64/T64, a SID given as PRG...), memory conflicts, texts that are
  too long or use characters the C64 screen cannot show. No tape is written while errors remain.
- **Presets** for emulators (fast / standard) and for a real datassette (normal / safe).
- **Memory map** showing where the PRG, SID, loader and free areas are.
- **No external dependencies**: just Python (plus `tkinter` for the GUI). It embeds its own mini 6502 assembler.

## Requirements

- Python 3.8+ (developed and tested with Python 3.12)
- For the GUI: `tkinter` (Debian/Ubuntu: `sudo apt install python3-tk`)
- Designed for **Linux**; it should work on Windows and macOS too but this has not been tested.

## Usage

```bash
python3 c64tap.py                 # graphical interface
python3 c64tap.py game.prg        # command line, creates game.tap
python3 c64tap.py game.prg --sid music.sid --song 1 --sid-reloc auto --preset emu \
    --title "MY GAME" --subtitle "Welcome!|Press play and enjoy"
python3 c64tap.py game.prg --check  # run the checks only
python3 c64tap.py --help
```

Description lines are separated with `|` on the command line (up to 10 lines of 38 characters); a single long sentence
is wrapped automatically.

| Preset | Speed | Block size | For |
|---|---|---|---|
| `emu-fast` | fast | 256 | VICE and similar, maximum speed (not for a real datassette) |
| `emu` | normal | 256 | emulators, MiSTer, BMC64 (recommended) |
| `tape` | normal | 256 | real datassette in good condition |
| `tape-safe` | slow | 128 | old datassettes or cassette recordings: slow but tolerant |

## Using the `.tap`

- **VICE**: attach the file as a tape image and press Play on the virtual datassette after `LOAD`. Because the turbo
  part reads the real pulses, **turn off the datassette "virtual device traps"** in the peripheral settings, otherwise
  VICE loads only the first file and skips the turbo part.
- **Real C64**: transfer the `.tap` to something the datassette port can read (for example convert it to a WAV file
  and record it to a cassette, or use a datassette emulator such as the TAPuino). Start with the *safe* preset.

## How it works

1. **Stage 1** - a standard KERNAL BASIC file (`10 SYS 2061`) containing only the turbo receiver (about 600 bytes).
2. **Stage 2** - loaded by the turbo receiver: the loading screen, the music driver and scene data.
3. **SID music** (if chosen) and **your program**, in blocks with pilot tone, marker, address, length and XOR checksum.
   Bit 0 and bit 1 are two pulse lengths different from the KERNAL ones, measured with CIA1 timer B.

When loading ends, the loader restores the system (`IOINIT`, `RESTOR`, `CINT`) and starts your program through its
`SYS`, with `RUN`, or at a given address.

Memory: the resident loader (about 1.4-2.4 KB) sits at `$C000` or in the first free area; the loader screen uses
`$0400-$07FF`; your PRG must live between `$0200` and `$CFFF` (not in `$0400-$07FF`), with at most 255 blocks; the
loader uses 32 zero-page bytes (`$E0-$FF`, moved elsewhere if the SID needs them).

## SID notes and known limits

- PSID files with a non-zero play address are supported. RSID and tunes that install their own IRQ are not.
- Relocation moves the tune by whole pages. The tune is run in the emulator until the set of address references stops
  growing, then the relocated tune is checked to produce exactly the same SID writes and no longer touch the original
  area. This is a practical check, not a proof: code the tune does not execute during the analysis is not verified.
- Tested with **VICE** only. Not yet tested on a real datassette or on NTSC machines (duration estimates are PAL).
- Digi-sample tunes and tunes driven by CIA timers are not played correctly.

## Troubleshooting

If the loader shows `ERRORE DI CARICAMENTO` ("loading error"), the line below reads `BLOCCHI xx/yy ERR zz`: blocks
received, expected and errors counted (hexadecimal). Try a slower preset; in an emulator check the "virtual device traps".

## Example

`examples/demo.prg` is a tiny program that prints a message, `examples/demo.tap` is the resulting tape image.

## Credits and license

Idea and testing: Linusvista. Developed with the assistance of Claude (Anthropic).
Released under the [MIT license](LICENSE). No game or tune is included in this repository. *Commodore 64* is a trademark
of its respective owners; this project is not affiliated with or endorsed by them.
