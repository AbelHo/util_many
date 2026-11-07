"""Real-Chromium multi-channel regression and main-thread interaction benchmark.

Run: python tests/audio_annotator_v2/run.py --suite multi_channel
The fixture is deterministic eight-channel PCM; no user audio is uploaded.
"""
import json
import math
import struct
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright
from common import F, OUT, launch, mount

F.mkdir(parents=True, exist_ok=True)
audio = F / 'multichannel_8ch_48k.wav'
if not audio.exists():
    rate, channels, frames = 48000, 8, 3 * 48000
    with wave.open(str(audio), 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        # Small enough to generate quickly while leaving channels audibly distinct.
        block = bytearray()
        for i in range(frames):
            for c in range(channels):
                sample = round(16000 * math.sin(2 * math.pi * (220 + 70 * c) * i / rate))
                block.extend(struct.pack('<h', sample))
            if i % 8192 == 8191:
                wav.writeframesraw(block)
                block.clear()
        wav.writeframes(block)

with sync_playwright() as playwright:
    browser = launch(playwright)
    page = browser.new_page(viewport={'width': 1440, 'height': 980}, accept_downloads=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    mount(page)

    def state():
        return page.evaluate('AudioAnnotatorV2.inspect()')

    def choices(*channels):
        for c in channels:
            page.locator(f'#channelChoices input[data-channel="{c}"]').check()

    def wave_rows(n):
        page.wait_for_function(
            '(count) => document.querySelectorAll("#plotStack > .channel-wave").length === count',
            arg=n,
        )

    def focus(ch):
        page.locator(f'#channelChoices button[data-focus-channel="{ch}"]').click()
        page.wait_for_function('(ch) => AudioAnnotatorV2.inspect().focusChannel === ch', arg=ch)

    def align():
        positions = page.evaluate('''() => [...document.querySelectorAll("#plotStack > .plot")]
            .map(plot => {
                const r = plot.querySelector("canvas").getBoundingClientRect();
                return [r.left + 64, r.right - 16];
            })''')
        assert max(p[0] for p in positions) - min(p[0] for p in positions) < 1.2, positions
        assert max(p[1] for p in positions) - min(p[1] for p in positions) < 1.2, positions

    page.locator('#fileInput').set_input_files(str(audio))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta?.channels === 8')
    assert state()['selectedChannels'] == [0]
    assert state()['focusChannel'] == 0
    assert page.locator('#channelChoices input[data-channel]').count() == 9  # 8 + Mix
    assert page.locator('#channelChoices input[data-channel="0"]').is_checked()
    assert not page.locator('#otherSpectrograms').is_checked()

    # Multi-select preserves detailed primary waveform and spectrogram.
    choices(1, 2, 3)
    wave_rows(3)
    assert state()['selectedChannels'] == [0, 1, 2, 3]
    assert page.locator('#plotStack > .channel-spec').count() == 0
    assert page.locator('#plotStack > .plot-resizer').count() == 4
    align()
    page.locator('#channel-wave-1').scroll_into_view_if_needed()
    page.wait_for_function('AudioAnnotatorV2.inspect().secondaryPreviewCount >= 1', timeout=20000)

    # Every extra row uses real marker geometry and shares the annotation timeline.
    page.locator('#addPointBtn').click()
    assert state()['markerCount'] == 1
    focus(2)
    wave_rows(3)
    assert state()['selectedChannels'] == [0, 1, 2, 3]
    assert state()['markerCount'] == 1
    page.wait_for_function('AudioAnnotatorV2.inspect().render?.fft === 2048', timeout=20000)
    focus(0)

    # Optional spectrograms are on-demand and remain aligned.
    page.locator('#otherSpectrograms').check()
    assert page.locator('#plotStack > .channel-spec').count() == 3
    align()
    page.locator('#channel-spec-1').scroll_into_view_if_needed()
    page.wait_for_function('''() => document.querySelector("#channel-spec-1 canvas:not(.overlay)")?.width > 0''')
    page.wait_for_function('''() => AudioAnnotatorV2.inspect().secondaryPreviewCount >= 2''', timeout=20000)

    # Select all physical channels; only nearby plots receive background rendering.
    page.locator('#channelSelectAll').click()
    wave_rows(7)
    assert state()['selectedChannels'] == list(range(8))
    assert page.locator('#plotStack > .channel-spec').count() == 7
    align()
    page.locator('#wavePlot').scroll_into_view_if_needed()

    # Measure UI event-to-next-animation-frame responsiveness with 8 waveforms
    # and 8 spectrograms; most are virtualized off-screen. Heavy native audio
    # and FFT work happens on the worker, not the browser main thread.
    metrics = page.evaluate('''async () => {
        const delays = [], longTasks = [];
        const observer = PerformanceObserver.supportedEntryTypes.includes('longtask') ?
            new PerformanceObserver(list => longTasks.push(...list.getEntries().map(x => x.duration))) : null;
        observer?.observe({ entryTypes: ['longtask'] });
        for (let i = 0; i < 50; i++) {
            const start = performance.now();
            document.getElementById(i % 2 ? 'zoomOut' : 'zoomIn').click();
            await new Promise(resolve => requestAnimationFrame(resolve));
            delays.push(performance.now() - start);
        }
        observer?.disconnect();
        delays.sort((a, b) => a - b);
        return { p50: delays[Math.floor(delays.length * .5)],
            p95: delays[Math.floor(delays.length * .95)],
            max: delays[delays.length - 1], longTasks: longTasks.length };
    }''')
    assert metrics['p95'] < 160, metrics
    assert metrics['max'] < 700, metrics

    # Remove a focused channel: another selected channel becomes the focus.
    focus(4)
    page.locator('#channelChoices input[data-channel="4"]').uncheck()
    page.wait_for_function('AudioAnnotatorV2.inspect().focusChannel !== 4')
    assert 4 not in state()['selectedChannels']

    # Mix is an explicit optional track (never an accidental playback mix).
    choices(-1)
    focus(-1)
    assert state()['focusChannel'] == -1
    assert -1 in state()['selectedChannels']

    # Only focused leaves one visible track; the final track cannot be unticked.
    page.locator('#channelSolo').click()
    wave_rows(0)
    assert state()['selectedChannels'] == [-1]
    page.locator('#channelChoices input[data-channel="-1"]').uncheck()
    assert state()['selectedChannels'] == [-1]
    assert page.locator('#channelChoices input[data-channel="-1"]').is_checked()

    # New file resets both focus and checked channels rather than carrying
    # indices over into a recording with fewer channels.
    page.locator('#fileInput').set_input_files(str(audio))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta?.channels === 8')
    assert state()['selectedChannels'] == [0]
    assert state()['focusChannel'] == 0
    assert page.locator('#plotStack > .channel-wave').count() == 0
    assert not errors, errors

    result = {'passed': True, 'events': 50, 'latencyMs': metrics,
              'browser': browser.version, 'pageErrors': errors}
    (OUT / 'multi-channel-results.json').write_text(json.dumps(result, indent=2))
    print('MULTI CHANNEL PASS: multi-select, focus, mix, optional FFT previews,'
          ' sync, annotation preservation, event-loop responsiveness', metrics)
    browser.close()
