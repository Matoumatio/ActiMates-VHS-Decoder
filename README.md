# ActiMates VHS Decoder

A research/reverse-engineering toolkit for extracting and identifying commands encoded as optical barcodes in ActiMates VHS tapes The barcode signal is embedded as a thin vertical strip in the video, which the toy reads to trigger synchronized responses

This project is **unfinished and experimental** — many things don't work correctly yet See the [Known Issues](#known-issues) section before using

---

## Tools

### `decode.py` — VHS Barcode Decoder

The main decoder application Opens a video file, locates the barcode strip frame by frame, extracts bits from pixel intensities, groups them into packets, hashes each packet (SHA-1), and logs the results Unknown commands are stored in a local database for later identification

### `analysis.py` — Command Database Manager

A companion GUI for managing the `commands.json` database produced by the decoder Lets you rename unknown command hashes, search and filter entries, view timestamps, and import/export to CSV

---

## Requirements

```
pip install opencv-python numpy
```

`tkinter` is required and is included with most Python 3 installations On Debian/Ubuntu, install it with:

```bash
sudo apt install python3-tk
```

---

## Usage

### Decoder

```bash
python decode.py
```

1. Click **Open Video** to load a VHS capture file
2. Click **Preview Frame** to see a random frame with the barcode region highlighted
3. Adjust the **Barcode Region Calibration** sliders until the green rectangle aligns with the barcode strip in the debug window
4. Set your desired **Speed** (frame skip) — higher values are faster but may miss short blinks
5. Click **Decode...** and optionally enable auto-export for SRT and WAV output
6. Click **Start Decode**

Decoded events are logged in the text area Results are saved to `commands.json` in the working directory

### Database Manager

```bash
python analysis.py
```

Opens `commands.json` automatically if present Double-click any entry to rename it Supports batch rename, find & replace, CSV import/export, and filtering by named/unknown status

---

## Output Files

| File | Description |
|------|-------------|
| `commands.json` | Database of hashed command packets and their names/timestamps |
| `*_decoded.srt` | SubRip subtitle file with command names and timestamps |
| `*_barcode.wav` | Audio representation of the barcode strip (spectrogram-style WAV) |

---

## Examples

These two videos show what the barcode audio export actually sounds like in practice The audio is extracted directly from the barcode strip column of the original VHS footage

**Example 1** — Raw barcode audio from a cartoon episode The background audio from the cartoon itself bleeds through, which is expected since the barcode strip is part of the same video signal:

[![ActiMates Barcode Audio Example 1](https://www.youtube.com/watch?v=BXEfCJNyvfI)]

**Example 2** — Raw barcode audio where the ActiMates plush responses are audible alongside the barcode signal, giving a clearer sense of the timing relationship between the signal and the toy's reactions:

[![ActiMates Barcode Audio Example 2](https://www.youtube.com/watch?v=qKrls2Ymwo4)]

---

## Known Issues

> ⚠️ This project is in early/experimental state Expect rough edges

**Decoding accuracy is unreliable** The bit extraction logic uses a simple per-line mean threshold, which is very sensitive to video quality, noise, and barcode alignment Even small calibration errors produce incorrect or inconsistent packet hashes

**The "blink" detection is fragile** The silence-based blink separator (`MIN_SILENCE_FRAMES = 5`) was chosen arbitrarily and will split or merge blinks incorrectly depending on the source material There is no validation that a detected blink corresponds to a real command

**Packet hashing is positional, not error-corrected** Packets are hashed as raw bit arrays A single flipped bit produces a completely different hash, meaning the same real command can appear under dozens of different hashes depending on noise

**Timestamp recording has a known mismatch bug** The code itself warns about this: after decoding, it prints a `WARNING: Timestamp mismatch!` if the number of timestamps recorded differs from those actually saved This has been observed in practice and the root cause is not yet resolved

**The barcode audio export doesn't represent commands** The WAV export converts raw pixel intensities to audio via linear interpolation — it's a spectrogram-style visualization, not a faithful audio encoding of the command signal It is useful for human inspection but not for programmatic analysis

**`bits_to_audio()` is defined but never called** A second audio encoding function exists in `decode.py` that converts bit arrays to square-wave audio, but it is unused and unreachable from the UI

**Frame skipping can silently miss commands** Using 5x, 10x, or 20x speed skips frames and will drop short blinks that don't span enough frames to survive the skip interval

**Ultra Fast mode disables all debug feedback** When "ULTRA FAST (No Preview)" is checked, the debug window is destroyed and no visual feedback is available while decoding runs

**The database manager's search only matches command names, not hashes** Looking up a specific hash requires scrolling manually or exporting to CSV

**No undo functionality** Renaming or batch-renaming commands in the database manager cannot be undone Always keep a backup of `commands.json`

**Packet boundaries are assumed, not detected** The decoder uses a fixed `PACKET_SIZE = 128` bits with no start/stop markers or alignment detection If the barcode data doesn't start on a packet boundary, all subsequent packets will be misaligned

---

## Configuration (in `decode.py`)

Key constants at the top of the file that may need tuning per source video:

| Constant | Default | Description |
|----------|---------|-------------|
| `BAR_X_OFFSET` | `0` | Horizontal start of barcode strip |
| `BAR_WIDTH` | `12` | Width of barcode strip in pixels |
| `LINES_IGNORE_TOP` | `10` | Lines to skip at top of strip |
| `LINES_IGNORE_BOTTOM` | `10` | Lines to skip at bottom of strip |
| `THRESHOLD_MODE` | `"adaptive"` | `"adaptive"` (mean) or `"fixed"` |
| `PACKET_SIZE` | `128` | Bits per packet |
| `MIN_SILENCE_FRAMES` | `5` | Frames of no signal to delimit a blink |
| `CONSTANT_SIGNAL_TOP_LINES` | `5` | Additional top lines treated as constant signal |

---

## License

No license specified This is a personal reverse-engineering research tool
