"""Chromium regressions for simultaneous channel spectrograms and scoped labels.

Run: python tests/audio_annotator_v2/run.py --suite multi_channel
Uses deterministic, local eight-channel PCM; no user audio is uploaded.
"""
import csv
import io
import json
import math
import struct
import wave

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

    def views():
        return page.evaluate('AudioAnnotatorV2.overlayDebug()')

    def open_picker():
        page.locator('#channelPicker').evaluate('(node) => node.open = true')

    def picker_box(ch, view):
        assert view in ('wave', 'spec')
        return page.locator(f'#channelChoices input[data-channel="{ch}"][data-view="{view}"]')

    def check_channel(ch, view=None):
        open_picker()
        for kind in ((view,) if view else ('wave', 'spec')):
            picker_box(ch, kind).check()

    def uncheck_channel(ch, view=None):
        open_picker()
        for kind in ((view,) if view else ('wave', 'spec')):
            picker_box(ch, kind).uncheck()

    def rows(n):
        page.wait_for_function(
            '(n) => document.querySelectorAll("#plotStack > .channel-wave").length === n && '
            'document.querySelectorAll("#plotStack > .channel-spec").length === n', arg=n)

    def align():
        positions = page.evaluate('''() => [...document.querySelectorAll("#plotStack > .plot")]
            .filter(plot => !plot.hidden)
            .map(plot => {
                const r = plot.querySelector("canvas").getBoundingClientRect();
                return [r.left + 64, r.right - 16];
            })''')
        assert max(p[0] for p in positions) - min(p[0] for p in positions) < 1.2, positions
        assert max(p[1] for p in positions) - min(p[1] for p in positions) < 1.2, positions

    def audacity(name, text, mode='merge'):
        page.locator('#importMode').select_option(mode)
        page.locator('#importInput').set_input_files({
            'name': name, 'mimeType': 'text/plain', 'buffer': text.encode()})
        page.locator('#importBtn').click()

    def source_count(n):
        page.wait_for_function('(n) => AudioAnnotatorV2.inspect().sources.length === n', arg=n)

    def marker_count(n):
        page.wait_for_function('(n) => AudioAnnotatorV2.inspect().markerCount === n', arg=n)

    page.locator('#fileInput').set_input_files(str(audio))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta?.channels === 8')
    assert state()['selectedChannels'] == [0]
    assert state()['selectedWaveChannels'] == [0]
    assert state()['selectedSpectrogramChannels'] == [0]
    assert state()['playbackChannels'] == [0]
    assert page.locator('#channelChoices input[data-view="wave"]').count() == 8
    assert page.locator('#channelChoices input[data-view="spec"]').count() == 8
    assert picker_box(0, 'wave').is_checked() and picker_box(0, 'spec').is_checked()
    assert not picker_box(1, 'wave').is_checked() and not picker_box(1, 'spec').is_checked()
    assert page.locator('#channelChoices .channel-head').inner_text().split() == ['Channel', 'Waveform', 'Spectrogram']
    assert page.locator('[data-focus-channel]').count() == 0
    assert page.locator('#otherSpectrograms').count() == 0

    for ch in [1, 2, 3]:
        check_channel(ch)
    rows(3)
    assert state()['selectedChannels'] == [0, 1, 2, 3]
    assert state()['playbackChannels'] == [0, 1, 2, 3]
    assert page.locator('#plotStack > .plot-resizer').count() == 7
    align()
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    page.wait_for_function(
        'AudioAnnotatorV2.inspect().secondarySpectrumChannels.includes(2)',
        timeout=25000)

    # Waveform and spectrogram can be switched independently for a channel.
    uncheck_channel(2, 'wave')
    assert state()['selectedWaveChannels'] == [0, 1, 3]
    assert state()['selectedSpectrogramChannels'] == [0, 1, 2, 3]
    assert state()['playbackChannels'] == [0, 1, 2, 3]
    assert page.locator('#channel-wave-2').count() == 0
    assert page.locator('#channel-spec-2').count() == 1
    uncheck_channel(3, 'spec')
    assert state()['selectedWaveChannels'] == [0, 1, 3]
    assert state()['selectedSpectrogramChannels'] == [0, 1, 2]
    assert state()['playbackChannels'] == [0, 1, 2, 3]
    assert page.locator('#channel-wave-3').count() == 1
    assert page.locator('#channel-spec-3').count() == 0
    assert page.locator('#plotStack > .plot-resizer').count() == 5
    align()
    # Re-enable both views before testing global imported label overlays.
    check_channel(2, 'wave')
    check_channel(3, 'spec')
    rows(3)

    # Audacity TXT does not contain channel IDs: overlay it on every spectrogram.
    audacity('global.txt', '0.5\t0.6\tGlobal label\n')
    source_count(1)
    marker_count(1)
    assert state()['markers'][0]['channel'] is None
    assert [views()['spectrogramsByChannel'][str(ch)] for ch in range(4)] == [1] * 4
    assert [views()['waveformsByChannel'][str(ch)] for ch in range(4)] == [1] * 4

    # A stacked label source remains on its own row when its spectral overlay
    # is disabled. Hiding a source is NOT a deletion or annotation edit.
    audacity('stack.txt', '1.0\t1.1\tStacked label\n', mode='stack')
    source_count(2)
    marker_count(2)
    assert views()['tracks'][0]['count'] == 1
    assert [views()['spectrogramsByChannel'][str(ch)] for ch in range(4)] == [2] * 4
    page.locator('#importSourceControls input').nth(1).uncheck()
    assert [views()['spectrogramsByChannel'][str(ch)] for ch in range(4)] == [1] * 4
    assert views()['tracks'][0]['count'] == 1
    assert page.locator('#plotStack > .label-track').count() == 1
    assert [views()['waveformsByChannel'][str(ch)] for ch in range(4)] == [1] * 4
    before_undo = state()['undo']
    page.locator('#importSourceControls input').nth(0).uncheck()
    assert [views()['spectrogramsByChannel'][str(ch)] for ch in range(4)] == [0] * 4
    assert [views()['waveformsByChannel'][str(ch)] for ch in range(4)] == [1] * 4
    assert views()['tracks'][0]['count'] == 1
    assert state()['undo'] == before_undo
    page.locator('#importSourceControls input').nth(0).check()

    # A JSON marker with an explicit 0-based channel appears only there.
    with page.expect_download() as dl:
        page.locator('#exportJson').click()
    source_doc = json.loads(dl.value.path().read_text())
    specific = dict(source_doc['markers'][0], id='specific-channel-2', sourceId=None,
                    channel=2, label='Only channel 3')
    source_doc['markers'] = [specific]
    source_doc['tags'] = []
    page.locator('#importMode').select_option('merge')
    page.locator('#importInput').set_input_files({
        'name': 'scoped.json', 'mimeType': 'application/json',
        'buffer': json.dumps(source_doc).encode()})
    page.locator('#importBtn').click()
    source_count(3)
    marker_count(3)
    assert [views()['spectrogramsByChannel'][str(ch)] for ch in range(4)] == [1, 1, 2, 1]
    assert [views()['waveformsByChannel'][str(ch)] for ch in range(4)] == [1, 1, 2, 1]
    page.locator('#importSourceControls input').nth(2).uncheck()
    assert [views()['spectrogramsByChannel'][str(ch)] for ch in range(4)] == [1] * 4
    assert [views()['waveformsByChannel'][str(ch)] for ch in range(4)] == [1, 1, 2, 1]
    assert views()['tracks'][0]['count'] == 1

    # Drawing directly on a non-primary spectrogram captures that channel
    # rather than unexpectedly placing the annotation on every channel.
    page.locator('input[name=mode][value=point]').check()
    canvas = page.locator('#channel-spec-1 canvas.overlay')
    canvas.scroll_into_view_if_needed()
    canvas.click(position={'x': 175, 'y': 94})
    marker_count(4)
    created = state()['markers'][-1]
    assert created['channel'] == 1, created
    assert page.locator('#editChannel option').count() == 9
    assert page.locator('#editChannel').input_value() == '1'
    page.locator('input[name=mode][value=navigate]').check()

    # Channel specificity survives both JSON and CSV exports.
    with page.expect_download() as dl:
        page.locator('#exportJson').click()
    exported = json.loads(dl.value.path().read_text())
    assert next(m for m in exported['markers'] if m['id'] == 'specific-channel-2')['channel'] == 2
    with page.expect_download() as dl:
        page.locator('#exportCsv').click()
    exported_rows = list(csv.DictReader(io.StringIO(dl.value.path().read_text())))
    assert next(r for r in exported_rows if r['id'] == "'specific-channel-2")['channel'] == '2'

    # Full eight-channel selection does not block UI. Non-visible FFT plots
    # are demand-rendered; the primary spectrogram remains detailed.
    open_picker()
    page.locator('#channelSelectAll').click()
    rows(7)
    assert state()['selectedChannels'] == list(range(8))
    assert state()['playbackChannels'] == list(range(8))
    align()
    page.locator('#wavePlot').scroll_into_view_if_needed()
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
    print('MULTICHANNEL GUI LATENCY', metrics, flush=True)

    # Spectrogram-only mode: hide ALL waveforms but keep analysis, display
    # and playback functioning on all eight selected spectral channels.
    for ch in range(8):
        uncheck_channel(ch, 'wave')
    assert state()['selectedWaveChannels'] == []
    assert state()['selectedSpectrogramChannels'] == list(range(8))
    assert state()['playbackChannels'] == list(range(8))
    assert page.locator('#wavePlot').is_hidden()
    assert page.locator('#plotStack > .channel-wave').count() == 0
    assert page.locator('#specPlot').is_visible()
    assert page.locator('#plotStack > .channel-spec').count() == 7
    assert page.locator('#plotStack > .plot-resizer').count() == 7
    align()

    # Waveform-only mode: hide ALL spectrograms, while keeping native
    # waveform analysis, marker overlays and playback available.
    open_picker()
    page.locator('#channelSelectAll').click()
    for ch in range(8):
        uncheck_channel(ch, 'spec')
    assert state()['selectedWaveChannels'] == list(range(8))
    assert state()['selectedSpectrogramChannels'] == []
    assert state()['playbackChannels'] == list(range(8))
    assert page.locator('#specPlot').is_hidden()
    assert page.locator('#plotStack > .channel-spec').count() == 0
    assert page.locator('#wavePlot').is_visible()
    assert page.locator('#plotStack > .channel-wave').count() == 7
    assert page.locator('#plotStack > .plot-resizer').count() == 7
    align()

    # Mixed-kind selection: waveform on Channel 1, spectrogram on
    # Channel 2. The primary spectral plot is hidden, but the second
    # channel's spectrogram still receives a real worker render.
    open_picker()
    page.locator('#channelSolo').click()
    uncheck_channel(0, 'spec')
    check_channel(1, 'spec')
    assert state()['selectedWaveChannels'] == [0]
    assert state()['selectedSpectrogramChannels'] == [1]
    assert state()['playbackChannels'] == [0, 1]
    assert page.locator('#wavePlot').is_visible()
    assert page.locator('#specPlot').is_hidden()
    assert page.locator('#channel-wave-1').count() == 0
    assert page.locator('#channel-spec-1').count() == 1
    assert page.locator('#plotStack > .plot-resizer').count() == 1
    align()
    page.locator('#channel-spec-1').scroll_into_view_if_needed()
    page.wait_for_function(
        'AudioAnnotatorV2.inspect().secondarySpectrumChannels.includes(1)',
        timeout=25000)
    uncheck_channel(0, 'wave')
    page.wait_for_function('AudioAnnotatorV2.inspect().referenceChannel === 1')
    assert state()['playbackChannels'] == [1]
    assert state()['selectedWaveChannels'] == []
    assert state()['selectedSpectrogramChannels'] == [1]
    assert page.locator('#wavePlot').is_hidden()
    assert page.locator('#specPlot').is_visible()
    assert page.locator('#plotStack > .channel-spec').count() == 0
    assert page.locator('#plotStack > .plot-resizer').count() == 0

    # The very last enabled view cannot be unticked: otherwise playback
    # would have no valid physical channel to use.
    open_picker()
    picker_box(1, 'spec').click()
    assert state()['selectedChannels'] == [1]
    assert picker_box(1, 'spec').is_checked()

    # Reset the selection and plots when opening a new recording.
    page.locator('#fileInput').set_input_files(str(audio))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta?.channels === 8')
    assert state()['selectedChannels'] == [0]
    assert state()['selectedWaveChannels'] == [0]
    assert state()['selectedSpectrogramChannels'] == [0]
    assert page.locator('#wavePlot').is_visible()
    assert page.locator('#specPlot').is_visible()
    rows(0)
    assert not errors, errors
    result = {'passed': True, 'events': 50, 'latencyMs': metrics,
              'browser': browser.version, 'pageErrors': errors}
    (OUT / 'multi-channel-results.json').write_text(json.dumps(result, indent=2))
    print('MULTI CHANNEL PASS: independent waveform/spectrogram checkboxes and playback, global and'
          ' scoped labels, source-only spectrum visibility, CSV/JSON, GUI responsiveness', metrics)
    browser.close()
