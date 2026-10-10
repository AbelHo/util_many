implementationIn [$github]() respository `util_many`:
Create a new `audio_annotatorv2.html` file with the following features below. Reference `video_frame_annotator.html` and use many similar things and features in it for especially for scrolling, annotating/labelling, etc.
Do not read or open the current `audio_annotator.html` or any previous older version of `audio_annotator.html`, do not read/open anything from `helper/audio_annotator.html` either. I want you to start this implementation from a clean slate and perspective. The previous implementation has some bugs that I don't want to happen again.
First use github `sample/251006_001_0002.WAV` for initial testing. After that test ALL the other larger files in [$google-drive]() Google Drive `audio` folder. Test them one by one, check if all the UI still works correctly and smoothly. Ensure sampling rate and display of half nyquist frequency automatically. 

Important notes and potential bugs you need to check and resolve. So you should take those into account during design:
- ultrasonic sampling rate compatibility
- very long recordings feasibility, it should not lag or crash the browser
- consider memory usage and performance optimizations for large files
- caching and/or preload for efficient scrubbing and scrolling

Fully test and run it on the browser to ensure all features are working correctly and smoothly. Then push all your work into a new branch in the repository.


-----------------------------
Audio Annotator: A browser-based tool for annotating audio files with synchronized time-series and spectrogram visualization.

Key Features:
- Upload audio via file input or drag & drop (no server, all client-side)
- Dual visualization: waveform (time-series) and spectrogram in parallel
- Playback controls with time scrubbing, play/pause, speed control
- Adjustable amplitude, sample rate display, and spectrogram settings
- Zoom and scroll through audio with synchronized views
- Annotation modes: Point, Time Range, and Frequency Range markers
- Markers stored with timestamps, with undo/redo support
- Export annotations as JSON or CSV (with metadata and all marker types)
- Import annotations from JSON or CSV files, with merge or replace option
- Audio analysis features: FFT size control, frequency range selection, color scale
- Minimal CSS, no build step, uses Web Audio API

Usage Instructions:
- Open the HTML file in a browser
- Load an audio file, adjust visualization settings as needed
- Select annotation mode, annotate regions as needed
- Use zoom/scroll controls to navigate audio
- Use Undo/Redo, clear, and export as required

Maintenance Notes:
- All logic is in this file (no external JS dependencies)
- Uses Web Audio API for audio processing and playback
- Audio is decoded at its NATIVE sample rate: a dedicated AudioContext is opened
&#x20; at the file's detected rate (ensureAudioContext) so high-sample-rate / ultrasonic
&#x20; recordings keep their full frequency band instead of being resampled to ~44.1 kHz
- Frequency Range controls (displayFreqMin/displayFreqMax) zoom the spectrogram's
&#x20; frequency axis; getDisplayFreqRange() resolves/clamps the band to [0, Nyquist]
- See README.md for project-wide conventions