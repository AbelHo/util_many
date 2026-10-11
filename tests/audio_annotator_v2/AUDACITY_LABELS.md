# Audacity label TXT interoperability — Audio Annotator v2

Audacity's **label TXT** is a UTF-8, tab-delimited plain-text format, **not** the
Audio Annotator's CSV interchange format. The importer accepts standard,
extended (spectral), and mixed records. Export defaults to *Extended* so
spectral annotations are not silently discarded.

## Format

Standard: one line per label:

~~~text
1.000000	1.000000	Point label
2.500000	4.500000	Time region
~~~

The first and second columns are **start** and **end** times in seconds.
When equal, the label is a **point**. The third column is the label text;
Audacity normally emits it even when empty. Audacity also accepts legacy
point lines of the form `start<TAB>label`, and even a start alone.
For a legacy two-field line whose second token parses as a number, Audacity
interprets it as **end time** rather than label text.

Extended: append one immediately following line **only for labels that
have a stored frequency selection**:

~~~text
1.000000	1.000000	Single spectral frequency
\	6928.456055	6928.456055
2.000000	2.500000	Upper frequency only
\	-1.000000	6334.588867
3.000000	3.500000	Lower frequency only
\	8908.015625	-1.000000
4.000000	4.500000	Frequency box
\	1484.669312	2969.338523
~~~

The continuation line has three tab-separated fields:
**literal backslash**, **low frequency (Hz)**, **high frequency (Hz)**.
`-1` denotes an undefined bound, not minus-one hertz. Defined values may
be equal, and one bound can be missing. Audacity ignores additional unknown
backslash-prefixed continuation lines, but **this importer rejects unsupported
extensions** so no metadata is silently discarded.

The format has no header, recording identifier, label IDs, tags, colors,
transparency, or multi-track metadata. Audacity exports labels from multiple
label tracks into the same file, losing the track boundaries.

## Implementation

- **Import:** Use the annotation Import file picker or drop one or more `.txt`
  files. Load the corresponding audio first. Merge and Replace use the same
  undoable transactions as JSON/CSV. All rows, including time range, frequency
  bounds, marker count and undo-size limits, are validated **before** changes.
  Out-of-audio times or frequencies outside the loaded audio's Nyquist range
  are rejected, not clipped without warning.
- **Export:** Click **Export Audacity TXT**. The **Audacity style** dropdown
  selects Standard (time only) or Extended (frequency information). Default is
  Extended. Standard warns before dropping frequency information.
- **Text:** Imports accept valid UTF-8, optional UTF-8 BOM, and CRLF, LF or CR
  line endings. Files with invalid UTF-8 fail rather than silently mangling
  non-ASCII labels. Tabs and line breaks *inside a label* cannot be represented
  reliably in Audacity TXT; export asks before replacing these with spaces,
  without altering the in-memory original.
- **Saving:** Audacity TXT export does **not** clear the unsaved-data indicator.
  Use JSON for a lossless project snapshot. CSV also stores application metadata.
- **Safety:** Malformed rows, unsupported continuations, invalid numeric
  values, excessive file size and out-of-bounds coordinates fail atomically;
  label strings render as text rather than HTML.

## Tests

Run the dedicated real-Chromium end-to-end suite (requires the repository's
sample WAV plus Playwright and test dependencies):

~~~bash
python tests/audio_annotator_v2/run.py --suite audacity_labels
~~~

Or include it with existing suites:

~~~bash
python tests/audio_annotator_v2/run.py
~~~

The test covers a UTF-8 BOM, Unicode, legacy point records, spectral bounds,
file picker, Standard and Extended downloads, roundtrip, malformed/oversized
coordinates, invalid UTF-8, drag-and-drop, undo/redo, and lossy-text warning.

## References

- [Audacity manual: Importing and Exporting Labels](https://manual.audacityteam.org/man/importing_and_exporting_labels.html)
- [Audacity manual: Import / Export Preferences](https://manual.audacityteam.org/man/import_export_preferences.html)
- [Audacity source: LabelStruct::Import / LabelStruct::Export](https://github.com/audacity/audacity/blob/master/au3/libraries/au3-label-track/LabelTrack.cpp)

SubRip (`.srt`), WebVTT (`.vtt`) and podcast-chapters JSON are separate
subtitle/chapter formats in Audacity, not label TXT, and are not handled by
this import/export button.
