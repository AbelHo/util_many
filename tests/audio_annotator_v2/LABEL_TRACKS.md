# Label imports and synchronized tracks

Use `audio_annotatorv2.html` directly in Chromium. Select an audio file before importing labels.

## Import modes

| Mode | Existing annotations | Waveform overlay | Spectrogram overlay | New row |
| --- | --- | --- | --- | --- |
| **Merge** | Preserved; new markers added | Yes | Yes | No |
| **Replace** | Cleared atomically, including tag definitions and existing stacked rows | Yes | Yes | No |
| **Stack** | Preserved; new markers added | No | Yes | One per imported label file |

Choose a mode from **Import as** for a single file in the picker. Selecting several files or dropping files into the page opens a **separate Merge / Replace / Stack choice for every file**. Replace is confirmed again before discarding annotations. Canceling an individual import leaves existing data intact.

Stacked rows appear between the waveform and spectrogram, with the same left/right plot margins, recording time window, cursor and pan/zoom controls. Clicking a row in Navigate mode seeks/selects; Point/Time range modes can create annotations in the corresponding imported source. Frequency ranges remain spectrogram-only. Every boundary has a draggable handle that changes the heights of the two neighboring rows while preserving their combined height, with an 88px minimum; keyboard-focused separators also accept Up/Down arrows.

The checkbox row directly below **Show annotations** / **Label text** contains one visibility toggle per imported file. Turning a source off hides its annotations on **all** drawing surfaces, including its stacked row and spectrogram overlay, without deleting its markers, tag definitions, table entries or export data. The global Show annotations control still hides all annotation geometry.

Each imported file gets a distinct `sourceId`; this is carried by imported markers and included in JSON and CSV output. JSON also includes a `sources` array; CSV metadata and the optional `source_id` field carry equivalent provenance. Old 15-column CSV files remain importable. Importing a JSON/CSV file assigns **one new source set** for that import according to the mode chosen; embedded historical source groups are provenance, rather than instructions to create extra rows. The Audacity TXT export remains flat, by Audacity format design, and does not retain source IDs.

Bulk imports, replacements, clear operations, undo and redo swap markers, tags, and source/track state together. Invalid, canceled, or mismatched imports do not partially change that state. Track heights are display state, not part of annotation exports or undo history.

## Browser test

The focused Chromium regression checks all three import modes, source hiding, synchronized positions, drag/keyboard resizing, selected-track navigation, undo/redo, failed-import atomicity, JSON provenance, and independent per-file choices when dropping multiple files.

```sh
python -m pip install playwright numpy soundfile
python -m playwright install chromium
python tests/audio_annotator_v2/run.py --suite label_tracks
```

For the broader small-fixture suite:

```sh
python tests/audio_annotator_v2/run.py
```

No recording is uploaded to a server. Browser tests use the included WAV sample and synthetic labels; they do not replace manual validation on long multichannel recordings.
