# Helper & tests for `audio_annotator.html`

Reference scripts used to **generate test data for** and **automatically test**
the [`audio_annotator.html`](../../audio_annotator.html) utility. They are not
needed to use the tool (it remains a single, dependency-free HTML file) — they
document how it was verified and let anyone re-run the checks.

The browser tests drive a **real headless Chromium** via
[Playwright](https://playwright.dev/): they upload the sample recording, click
buttons, drag on the canvases, handle dialogs, capture downloads, and read back
canvas pixels / DOM text to assert behaviour.

## Contents

| File | Purpose |
|------|---------|
| `gen_wav.js` | Generates the demo recording `sample/251006_001_0002.WAV` (96 kHz, mono, 16-bit, 3 s). |
| `full_test.js` | Comprehensive functional suite — 29 checks across the whole flow. |
| `stress_test.js` | Robustness/performance — rapid-change convergence, 8192-pt FFT, all color scales. |
| `multirate_test.js` | Loads 96 k → 48 k → 96 k in sequence; verifies the AudioContext is re-opened at each file's native rate. |
| `decode_probe.js` | Diagnostic showing *why* native-rate decoding is needed (default context resamples to ~44.1 kHz). |

## The sample recording

`gen_wav.js` synthesises a bioacoustic-style clip with content across the whole
0–48 kHz band so every feature is exercised:

- `0.20–0.55 s` — descending chirp **20 kHz → 5 kHz**
- `0.80–1.05 s` — steady tone burst at **8 kHz**
- `1.25–1.70 s` — ascending chirp **2 kHz → 40 kHz** (exercises the high band)
- `1.85 / 1.95 / 2.05 s` — three broadband **clicks**
- `2.35–2.85 s` — two simultaneous tones **10 kHz + 25 kHz**
- low-level broadband background noise throughout

The content above ~24 kHz is the part that proves **native sample-rate
decoding** works — a default 44.1 kHz `AudioContext` would discard it.

## Prerequisites

- **Node.js** 18+
- **Playwright** with a Chromium build available to `require('playwright')`.

```bash
# from the repo root
npm install playwright            # or: npm i -g playwright
npx playwright install chromium   # if Chromium isn't already present
```

If Playwright is installed in a non-local location, point Node at it, e.g.
`NODE_PATH=/path/to/global/node_modules node helper/audio_annotator.html/full_test.js`.

## Running

```bash
# (re)generate the sample recording into ../../sample/
node helper/audio_annotator.html/gen_wav.js

# functional + stress suites (exit code 0 = all passed)
node helper/audio_annotator.html/full_test.js
node helper/audio_annotator.html/stress_test.js

# extra checks
node helper/audio_annotator.html/multirate_test.js
node helper/audio_annotator.html/decode_probe.js
```

Screenshots / temp files are written to `$OUT` (default:
`<os-tmp>/audio_annotator_test`) so the repo stays clean. Override with
`OUT=/some/dir node helper/audio_annotator.html/full_test.js`.

## What is tested

### `full_test.js` (29 checks)

- **Audio info / native decode** — duration, **sample rate shown as 96,000 Hz
  (not resampled)**, channels, **bit depth read from the WAV header**, freq-max
  input initialised to Nyquist (48000).
- **Spectrogram quality** — image has real structure (variance), and there is a
  bright signal line above 24 kHz over a dark background (high-frequency content
  survived native decoding).
- **Frequency-range selection** — apply a 20 k–48 k band, then "Full" reset.
- **FFT size & color scale** — change FFT size and switch color scales.
- **Annotations** — create a **Point** (spectrogram click, records frequency),
  a **Time Range** (waveform drag), and a **Frequency Range** (Shift+drag on the
  spectrogram); the list shows all three marker types.
- **Undo / redo** — remove and restore the last marker.
- **Export** — JSON parses and contains `meta` (filename + sampleRate) and all
  three marker types; CSV has the correct header, one row per marker, including
  the `freqRange` row.
- **Import** — *merge* adds valid records and silently skips malformed ones;
  *replace* swaps the set; the import is undoable.
- **Playback** — the clock advances on Play and resets on Stop.
- **Zoom** — zoom-in updates the level; reset returns to 100 %.
- **No uncaught page/console errors** at any point.

### `stress_test.js`

- Rapid back-to-back **color-scale** changes converge to the *last* selection.
- Grayscale renders neutral (r≈g≈b).
- Rapid back-to-back **FFT-size** changes converge to the *last* selection
  (8192), the image still has structure, and it renders in a reasonable time
  (typically ~0.9 s, asserted < 10 s).
- All four color scales (`viridis`, `cool`, `grayscale`, `hot`) render.
- No page/console errors during the stress sequence.

### `multirate_test.js`

- Loading 96 k → 48 k → 96 k re-opens the `AudioContext` at each file's native
  rate (the displayed sample rate follows the file), and playback still works
  after the context is recreated.

### `decode_probe.js`

- Confirms that a default `AudioContext` resamples the 96 kHz file (to ~44.1 kHz
  here) while an explicit `AudioContext({ sampleRate: 96000 })` preserves it —
  the basis for the app's `ensureAudioContext()`.

## Findings & fixes (from this testing)

These issues were found by running the tool in a browser and were fixed in
`audio_annotator.html`:

1. **High frequencies were silently lost** — audio was resampled to the
   hardware rate on decode. Now decoded at the file's **native sample rate**.
2. **Aliasing "X" artifacts** — the approximate decimating DFT was replaced with
   a true **radix-2 FFT** for an accurate spectrogram.
3. **"Frequency range selection" was documented but missing** — added a Freq
   Range (min–max Hz) control with a "Full" reset.
4. **Washed-out display** — spectrogram now **auto-scales to relative dB**
   (percentile noise floor) and defaults to the **viridis** color scale.
5. **Hardcoded axis labels / "16-bit"** — frequency labels are now dynamic and
   outlined; bit depth is read from the WAV header.
6. **Fragile import** — records are validated/sanitised, malformed rows skipped,
   quoted CSV handled, and imports are undoable.
7. **Race on rapid control changes** — each spectrogram pass snapshots its
   settings and recomputes if anything changed, so the view can't be corrupted
   or left stale.

## Notes

- The tests run headless; Web Audio works without an audio device, so playback
  checks only assert the transport clock and absence of errors.
- `file://` blocks `fetch`, so `decode_probe.js` injects the WAV bytes as base64.
