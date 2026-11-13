"""Chromium regression for synchronized multichannel pan/zoom/seek and FFT detail.

Run: python tests/audio_annotator_v2/run.py --suite multichannel_sync
Eight synthetic, frequency-distinct channels exercise real FFTs and plotting.
"""
import json
import math
import struct
import wave

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from common import F, OUT, launch, mount

F.mkdir(parents=True, exist_ok=True)
audio = F / 'multichannel_sync_8ch_48k.wav'
if not audio.exists():
    rate, channels, frames = 48000, 8, 3 * 48000
    with wave.open(str(audio), 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for start in range(0, frames, 2048):
            data = bytearray()
            for i in range(start, min(start + 2048, frames)):
                for ch in range(channels):
                    v = round(14000 * math.sin(2 * math.pi * (220 + ch * 70) * i / rate))
                    data.extend(struct.pack('<h', v))
            wav.writeframesraw(data)

with sync_playwright() as playwright:
    browser = launch(playwright)
    page = browser.new_page(viewport={'width': 1440, 'height': 980})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    mount(page)

    def state():
        return page.evaluate('AudioAnnotatorV2.inspect()')

    def channel(ch, kind, checked):
        page.locator('#channelPicker').evaluate('(x) => x.open = true')
        box = page.locator(f'#channelChoices input[data-channel="{ch}"][data-view="{kind}"]')
        box.check() if checked else box.uncheck()

    def view(ch):
        return state()['secondaryRenders'].get(str(ch))

    def refined(ch, *, spectrum=True, waveform=None, min_height=0):
        try:
            page.wait_for_function('''({ch, spectrum, waveform, height}) => {
            const s = AudioAnnotatorV2.inspect(), v = s.secondaryRenders[String(ch)];
            if (!v || !v.detailed || v.preview || !v.coversWindow || v.width < 500)
                return false;
            if (spectrum && (v.columns < 100 || v.height < Math.max(64, height)))
                return false;
            if (!spectrum && v.columns !== 0) return false;
            if (waveform === true && v.mode === 'hidden') return false;
            if (waveform === false && v.mode !== 'hidden') return false;
            return !s.renderPending;
            }''', arg={'ch': ch, 'spectrum': spectrum, 'waveform': waveform,
                       'height': min_height}, timeout=35000)
        except PlaywrightTimeout:
            debug = page.evaluate('''() => ({
                inspect: AudioAnnotatorV2.inspect(), status: document.getElementById('status').textContent,
                renderInfo: document.getElementById('renderInfo').textContent,
                plots: [...document.querySelectorAll('#plotStack > .channel-wave, #plotStack > .channel-spec')]
                    .map(p => ({ id: p.id, top: p.getBoundingClientRect().top,
                        height: p.getBoundingClientRect().height }))
            })''')
            print('SYNC TIMEOUT DEBUG', json.dumps(debug, default=str)[:22000], flush=True)
            raise
        return view(ch)

    page.locator('#fileInput').set_input_files(str(audio))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta?.channels === 8')
    assert state()['secondaryWorkerActive'], 'Dedicated worker must initialize'
    page.locator('#channelPicker').evaluate('(x) => x.open = true')
    page.locator('#channelSelectAll').click()
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    initial = refined(2)
    assert initial['width'] > 500, initial
    assert initial['columns'] > 100, initial
    # Its waveform row may be offscreen: avoid demanding samples for
    # a nonvisible view when only the spectrogram is on screen.
    assert state()['playbackChannels'] == list(range(8))
    print('SYNC all-selected full-resolution spectrum', initial, flush=True)

    # The old waveform-only implementation stayed at 320px previews forever.
    channel(1, 'spec', False)
    page.locator('#channel-wave-1').scroll_into_view_if_needed()
    wave_only = refined(1, spectrum=False, waveform=True)
    assert wave_only['width'] > 500 and wave_only['mode'] in ('exact', 'samples', 'indexed'), wave_only
    assert wave_only['columns'] == 0 and wave_only['height'] == 0, wave_only
    print('SYNC waveform-only native detail', wave_only, flush=True)

    # The opposite configuration must skip waveform work, without stale
    # waveform buffers entering the spectrum-only plot.
    channel(2, 'wave', False)
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    spectrum_only = refined(2, spectrum=True, waveform=False)
    assert spectrum_only['mode'] == 'hidden', spectrum_only

    # Resizing a *secondary* spectrum must change its worker pixel height.
    # Resizing must not invalidate the primary view cache or leave a blurry,
    # upscaled stale spectrum.
    before_height = spectrum_only['height']
    page.locator('#channel-spec-2').evaluate('(el) => el.style.height = "360px"')
    page.wait_for_function('''({height}) => {
        const s = AudioAnnotatorV2.inspect(), v = s.secondaryRenders['2'];
        return v && v.detailed && v.coversWindow && v.height >= height + 100;
    }''', arg={'height': before_height}, timeout=35000)
    resized = view(2)
    assert resized['height'] >= before_height + 100, (before_height, resized)
    print('SYNC resized spectrum geometry', before_height, resized['height'], flush=True)

    # Shrink the time window and perform numerous *asynchronous* pans to
    # reproduce worker cancellation/race conditions during real wheel input.
    page.locator('#windowSeconds').fill('0.45')
    page.locator('#windowSeconds').dispatch_event('change')
    page.evaluate('''async () => {
        const slider = document.getElementById('scrollSlider');
        for (let i = 0; i < 28; ++i) {
            slider.value = String(0.15 + (i % 9) * 0.19);
            slider.dispatchEvent(new Event('input', {bubbles: true}));
            await new Promise(resolve => setTimeout(resolve, 14));
        }
        slider.value = '1.4';
        slider.dispatchEvent(new Event('input', {bubbles: true}));
    }''')
    page.wait_for_function('Math.abs(AudioAnnotatorV2.inspect().start - 1.4) < .01')
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    after_pan = refined(2, spectrum=True, waveform=False, min_height=before_height + 100)
    assert after_pan['start'] <= 1.4 + 1e-8
    assert after_pan['start'] + after_pan['span'] >= 1.85 - 1e-8
    print('SYNC 28 rapid pan changes recovered detailed view', after_pan, flush=True)

    # Small pans inside the already rendered 25% margins should reuse the
    # same full-resolution pixels, not launch another expensive FFT per channel.
    old_frame = after_pan['frame']
    page.evaluate('''() => {
        const slider = document.getElementById('scrollSlider');
        slider.value = '1.44';
        slider.dispatchEvent(new Event('input', {bubbles: true}));
    }''')
    page.wait_for_function('Math.abs(AudioAnnotatorV2.inspect().start - 1.44) < .01')
    page.wait_for_timeout(350)  # let the secondary scheduler check the cached coverage
    after_small_pan = refined(2, spectrum=True, waveform=False, min_height=before_height + 100)
    assert after_small_pan['frame'] == old_frame, (after_pan, after_small_pan)
    print('SYNC overscan reused full-resolution frame across small pan', old_frame, flush=True)

    # Zoom, scrub outside the current window and confirm the secondary image
    # catches up to the new visible time interval, not just the primary ruler.
    page.locator('#zoomIn').click()
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    zoomed = refined(2, spectrum=True, waveform=False, min_height=before_height + 100)
    assert zoomed['span'] < after_pan['span']
    page.locator('#scrubSlider').evaluate('''slider => {
        slider.value = '2.55';
        slider.dispatchEvent(new Event('input', {bubbles: true}));
    }''')
    page.wait_for_function('AudioAnnotatorV2.inspect().cursor >= 2.5')
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    scrubbed = refined(2, spectrum=True, waveform=False, min_height=before_height + 100)
    assert scrubbed['start'] <= state()['start'] + 1e-8
    print('SYNC zoom + out-of-view scrub', zoomed, scrubbed, flush=True)

    # A filter edit must propagate to all three workers, including secondaries.
    page.locator('#highPassHz').fill('400')
    page.locator('#highPassHz').dispatch_event('change')
    page.wait_for_function('AudioAnnotatorV2.inspect().audioFilter?.high === 400', timeout=35000)
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    filtered = refined(2, spectrum=True, waveform=False, min_height=before_height + 100)
    diagnostics = page.evaluate('AudioAnnotatorV2.diagnostics()')
    assert diagnostics['analysis']['filter']['high'] == 400
    assert diagnostics['playback']['filter']['high'] == 400
    assert diagnostics['secondary']['filter']['high'] == 400
    print('SYNC filter across independent workers', filtered, flush=True)

    # Retained secondary images and annotation overlay rasters have strict
    # byte budgets even if many channels are selected or navigated repeatedly.
    budget = state()
    assert budget['secondaryImageCacheBytes'] <= 24 * 1048576, budget['secondaryImageCacheBytes']
    assert budget['annotationRasterCacheBytes'] <= 32 * 1048576, budget['annotationRasterCacheBytes']
    print('SYNC cache budgets (MiB)', {
        'secondary': round(budget['secondaryImageCacheBytes'] / 1048576, 2),
        'overlays': round(budget['annotationRasterCacheBytes'] / 1048576, 2)}, flush=True)

    # The button must build *every selected channel's* waveform + spectral
    # overview, not just the reference channel. Check both checkbox columns
    # and require secondary pooled spectral rendering after index completion.
    page.locator('#channelPicker').evaluate('(node) => node.open = true')
    page.locator('#channelSolo').click()
    for ch in (1, 2):
        channel(ch, 'wave', True)
        channel(ch, 'spec', True)
    page.locator('#channelPicker').evaluate('(node) => node.open = false')
    page.locator('#fftSize').select_option('32')
    page.locator('#rememberOverview').uncheck()
    page.wait_for_function('AudioAnnotatorV2.inspect().overview.fft === 32', timeout=30000)
    page.locator('#fitBtn').click()
    assert state()['selectedChannels'] == [0, 1, 2]
    page.locator('#overviewBtn').click()
    page.wait_for_function('''() => {
        const s = AudioAnnotatorV2.inspect();
        return s.overview.complete && s.overviewBatch?.complete &&
            s.overviewBatch.channels.join(',') === '1,2' &&
            s.overviewBatch.completed.join(',') === '1,2' &&
            Math.abs(Number(document.getElementById('overviewProgress').value) - 1) < 1e-8;
    }''', timeout=120000)
    batch = state()['overviewBatch']
    status = page.locator('#overviewInfo').inner_text()
    assert '3/3 selected channels indexed' in status, status
    stats = page.evaluate('AudioAnnotatorV2.diagnostics()')
    assert 0 in stats['analysis']['overviewChannels'], stats
    assert all(ch in stats['secondary']['overviewChannels'] for ch in (1, 2)), stats
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    page.wait_for_function('''() => {
        const s = AudioAnnotatorV2.inspect(), v = s.secondaryRenders['2'];
        return v?.detailed && v.coversWindow && v.spectrumMode === 'pooled';
    }''', timeout=35000)
    pooled = view(2)
    assert pooled['spectrumMode'] == 'pooled', pooled
    print('SYNC all-selected overview indexing PASS', batch, pooled, flush=True)

    assert not errors, errors
    result = {'passed': True, 'selectedOverviews': batch, 'indexedSpectrum': pooled,
              'initial': initial, 'waveOnly': wave_only,
              'spectrumOnly': spectrum_only, 'resized': resized,
              'rapidPan': after_pan, 'cachedPan': after_small_pan, 'zoom': zoomed, 'scrub': scrubbed,
              'filter': filtered, 'browser': browser.version, 'pageErrors': errors}
    (OUT / 'multichannel-sync-results.json').write_text(json.dumps(result, indent=2))
    print('MULTICHANNEL SYNCHRONIZATION PASS: preview/refinement, native detail,'
          ' resize geometry, rapid pan, zoom, seek, filter and playback selection', flush=True)
    browser.close()
