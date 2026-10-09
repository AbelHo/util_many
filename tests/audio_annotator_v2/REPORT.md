# Audio Annotator v2 — implementation and validation report

## Status

Implemented as `audio_annotatorv2.html`, an independent, single-file HTML/CSS/JavaScript utility. No external runtime dependencies, server, build step, or network requests are needed. The video annotator supplied navigation, held-key tag, color, and history conventions. Existing utilities and the generated root README are unchanged.

**Executed:** 18 native-decoder file cases, 200 browser interaction checks (25 checks on each of 8 files), and 12 targeted regression groups. All passed in the final run. The browser reported no uncaught page errors. Requests observed by the browser were local Blob worker URLs, not HTTP requests.

**Not executed:** three original Google Drive recordings exceeded the connector's 268,435,456-byte (256 MiB) download limit. Each was attempted separately and returned HTTP 413. Their original bytes were not available to this workspace. Synthetic tests do not certify those three recordings.

Validation date: 2026-10-07. Browser: headless Chromium **144.0.7559.96**, Linux. Playwright exercised actual File objects, Blob workers, canvases, pointer/keyboard events, downloads, and Web Audio nodes. Workspace policy blocked both `file://` and local HTTP navigation, so this run explicitly injected the complete HTML into a real browser page with `page.set_content`. Direct local-file navigation, other browser engines, physical sound hardware, and subjective listening were **not** verified here. The runner defaults to a real `file://` open outside this restricted environment.

Tested HTML Git blob: `0f821b441d6b77140541f0ce799ab764370bb7a2`.

Tested HTML SHA-256: `1006171d79968c42996f433d44337c407f5ec199dc7313e94cffe19faa375edf`.

## Requested recordings

| Source / recording | Bytes | Native sample rate | Channels | Duration | Result |
|---|---:|---:|---:|---:|---|
| GitHub `sample/251006_001_0002.WAV` | 576,044 | 96,000 Hz | 1 | 3 s | PASS; first case |
| Drive `synth.WAV` | 576,044 | 96,000 Hz | 1 | 3 s | PASS, separately loaded |
| Drive `FKW_small.wav` | 10,506,152 | 96,000 Hz | 1 | 54.7193125 s | PASS |
| Drive `20251006_14.39.58_log.flac` | 482,019,021 | Not inspected | Not inspected | Not inspected | BLOCKED: connector download limit |
| Drive `251006_001_0002.WAV` | 2,145,570,362 | Not inspected | Not inspected | Not inspected | BLOCKED: connector download limit |
| Drive `8746.250503152639.wav` | 1,715,006,124 | Not inspected | Not inspected | Not inspected | BLOCKED: connector download limit |

The accessible `synth.WAV` has Git blob hash `37f1c44bc6532949a9236d31301ae4be68bb8c04`, exactly matching GitHub's sample metadata. Those byte-identical bytes were used under the GitHub sample path for the initial case. This is **not** the much larger Drive original with the same filename. No private audio, Drive identifiers, or download credentials are committed with these tests.

## Additional synthetic fixtures and independent checks

Native PCM was compared with Python soundfile/libsndfile at the start, midpoint, and end of every numeric-test file, for every channel, plus channel averaging. The maximum measured per-channel float32 difference was **zero** in all 18 file cases. The mix comparison tolerance was 2e-7. This samples representative windows; it is not a claim that every sample of every multi-gigabyte file was compared.

The fixture suite covers unsigned PCM8, PCM16/24/32, float32/64 WAV, extensible WAV with 24 valid bits in a 32-bit container and odd padded metadata, mono/stereo/four-channel 24-bit FLAC, and 16-bit FLAC silence, constant, noise and sine residual cases. Native rates exercised were 96, 192, 384, 768 and 1,536 kHz.

| Stress fixture | Logical size | Rate / channels | Purpose |
|---|---:|---|---|
| `large_noise_7min.flac` | 484,074,166 bytes | 192 kHz / 2 | Actual densely encoded 24-bit FLAC, 420 s; decode, seek, render, annotate, play |
| `sparse_2145MB.wav` | 2,145,570,362 bytes | 96 kHz / 1 | RIFF with trailing metadata; 11,174.845354 s; offset and long-duration tests |
| `sparse_4_8GB_rf64.wav` | 4,800,000,080 bytes | 384 kHz / 2 | 64-bit RF64 sizes above 4 GiB; known first/middle/last sample pulses; 3,125 s |
| `native_1536k.wav` | 4,608,044 bytes | 1,536 kHz / 1 | Analysis beyond the tested browser's AudioContext rate limit |

The large WAV fixtures are deliberately sparse synthetic files. They test actual large File sizes, range reads, indexing, seeking, UI behavior and resource bounds, but do not reproduce every characteristic of the inaccessible original field recordings.

An 8192-point native Hann FFT was compared with NumPy: 100 kHz and 150 kHz signals peaked at **99,984.375 Hz** and **150,000 Hz**, respectively; maximum spectrum difference was **0.000007639 dB**. The first difference from the nominal tone is FFT bin spacing, not resampling.

A 1.536 MHz source retained a **768 kHz Nyquist display band** while the playback AudioContext fell back to **44,100 Hz**. In the actual browser audio graph, a 400 kHz source tone at 0.025x playback speed produced a measured peak of **10,002.17 Hz**. Changing volume from -12 dB to -24 dB produced a measured amplitude ratio of **0.251187**, as expected. These are software signal measurements, not a physical speaker/listening test.

## Browser interaction coverage

Each of the three accessible requested files and five additional stress/rate fixtures completed these 25 checks:

1. Native metadata and automatic Nyquist reset on file replacement.
2. Uppercase held-key tagging immediately after selecting a mode, without accidentally shift-deleting.
3. Waveform and frequency-point markers.
4. Reversed time-range drag normalization.
5. Reversed time/frequency box normalization and Hz bounds.
6. Undo/redo marker creation.
7. Selected-marker editing.
8. Tag name, color and alpha editing.
9. JSON and CSV downloads with metadata.
10. Undo/redo clear.
11. Exact CSV round-trip for all marker types, tags and colors.
12. JSON merge with collision-safe IDs and undo.
13. Filtering by tag display name.
14. Invalid import rejected atomically.
15. Window zoom and synchronized panning.
16. Ctrl+wheel time zoom.
17. Wheel pan.
18. Alt+wheel frequency zoom.
19. Frequency clamping and full-band restoration.
20. FFT size, color map, dB limits and waveform amplitude controls.
21. Twenty-five superseding view/FFT changes settle at the latest request, not stale worker results.
22. Slow playback, forward time progression, and stable pause position.
23. Exact end-of-file stop.
24. Stop returns to time zero.
25. Cache budgets remain within their configured limits.

The twelve additional regression groups cover native FFT accuracy and channel/mix UI; extensible WAV; exact overview completion and large-file pause/resume; multiline/Unicode/formula-safe CSV and plain-text DOM rendering; cancelled replacement/mismatched imports; keyboard deletion/history, hit bounds and Escape; malformed audio and recovery; actual DataTransfer drag/drop; large-FLAC responsiveness and 480-pixel layout; rapid native-rate changes and file replacement; real Web Audio slowdown/volume; and corrupt FLAC CRC rejection with recovery.

## Resource behavior and measured performance

Audio is not decoded into a whole-file AudioBuffer. Native PCM reads and the FLAC decoder run in inline workers, separately from playback scheduling. Analysis uses the original file rate; `ensureAudioContext()` is only responsible for playback output. Unsupported output rates therefore do not discard ultrasound from the spectrogram.

Configured retained-cache bounds are **8 MiB raw bytes per worker**, **12 MiB decoded FLAC frames per worker**, **32 MiB analysis FFT results**, and small bounded FFT/rate-conversion plans. Undo/redo transactions have a 16 MiB / 200-operation budget. Playback has a separate worker, approximately 0.9 s of lookahead, and at most 262,144 native source frames per chunk. These are component budgets, **not** a claim that total browser-process memory is their simple sum; temporary arrays, canvases, browser internals and object overhead are additional.

During the numeric RF64 case, the analysis worker read about **32.2 MB** of source bytes across its tested operations, rather than allocating the 4.8 GB recording. The exact waveform overview for `FKW_small.wav` occupied **518,824 bytes**.

A cold, whole-recording view of the dense 484 MB FLAC took **5.880 s** to finish in the final responsiveness regression. While that worker job ran, a 16 ms main-thread timer had a **16.1 ms 95th-percentile interval** and a **30.2 ms maximum interval** over 393 samples. Thus the UI stayed responsive in that test, but the final full-recording image was not instantaneous. Cached/narrow views are substantially less work; measurements depend on CPU, filesystem, browser and cache state.

## Accuracy and compatibility limits

- Wide waveform previews explicitly say **sampled** and can miss isolated peaks. Build exact overview scans cooperatively into a bounded min/max index. Indexed bins preserve peaks but can extend slightly beyond a screen pixel's interval.
- Wide spectrograms sample time columns; they are not exhaustive transient detectors. Zoom in for event annotation. Frequency bins are native-rate, Hann-windowed, peak-bin dBFS rather than a calibrated PSD.
- The 64-tap windowed-sinc playback converter is a finite filter, not an ideal brick-wall filter. Slowing down changes pitch. Hardware/output conversion and physical frequency response are distinct from analysis accuracy.
- Source formats are WAV/RF64/BW64 PCM/float and native FLAC. Other formats need conversion to WAV/FLAC first. FLAC requires a known total sample count. Ogg-FLAC, changing stream formats, and malformed or unusually oversized blocks are rejected explicitly.
- JSON/CSV use the explicit v2 annotation schema; no automatic conversion of unspecified legacy annotation formats is attempted.
- Annotations are bounded at 50,000, tags at 2,000, and the table is paginated. Overlays cap dense visible marker drawing and display a warning; export retains all stored annotations.
- Save regularly with Export. The tool does not silently write to local disk or upload anything.

## Reproduction

The HTML has no dependencies. The following Python packages are only for tests:

```sh
python -m pip install playwright numpy soundfile
python -m playwright install chromium
python tests/audio_annotator_v2/run.py --large
```

To test all original Drive recordings after downloading them locally, repeat `--audio`. No connector or server is involved:

```sh
python tests/audio_annotator_v2/run.py --large \
  --audio "/path/to/audio/synth.WAV" \
  --audio "/path/to/audio/FKW_small.wav" \
  --audio "/path/to/audio/20251006_14.39.58_log.flac" \
  --audio "/path/to/audio/251006_001_0002.WAV" \
  --audio "/path/to/audio/8746.250503152639.wav"
```

Use `--fixture-dir PATH` to choose where generated audio, screenshots, downloaded exports and JSON result reports live. `--chromium PATH` selects a browser executable. `--inject-html` is an explicit restricted-CI workaround, not the default. Without `--large`, the runner generates the small fixtures and runs the numeric and interaction suites; the additional large-file regression suite requires `--large`.

Large fixture creation needs about 550 MB of physical disk on a sparse-file filesystem; other filesystems may allocate the full roughly 7.5 GB logical size. Existing fixtures are reused. `fixtures.py DIRECTORY --large --overwrite` regenerates them explicitly.

## Maintainer map

`audio-worker` contains bounded byte access, WAV/RF64 parsing, native FLAC frame decoding/CRC/seeking, FFT/envelope generation, overview indexing, playback conversion, cancellation and worker RPC. The main script contains output-context lifecycle, bounded playback scheduling, synchronized rendering, pointer/keyboard interactions, validation, transaction history and JSON/CSV interchange.

`window.AudioAnnotatorV2` exposes read-only diagnostics used by the harness: `inspect()`, `readNativeSamples()`, `readSpectrum()`, `diagnostics()`, and `audioRMS()`. It does not expose a mutable application state or a network API.
