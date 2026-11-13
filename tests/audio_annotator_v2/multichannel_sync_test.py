"""Chromium regression for synchronized multichannel pan/zoom/seek and FFT detail.

Run: python tests/audio_annotator_v2/run.py --suite multichannel_sync
Eight synthetic, frequency-distinct channels exercise real FFTs and plotting.
"""
import json
import math
import struct
import wave

from playwright.sync_api import sync_playwright
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

    def refined(ch, *, spectrum=True, waveform=True, min_height=0):
        page.wait_for_function('''({ch, spectrum, waveform, height}) => {
            const s = AudioAnnotatorV2.inspect(), v = s.secondaryRenders[String(ch)];
            if (!v || !v.detailed || v.preview || !v.coversWindow || v.width < 500)
                return false;
            if (spectrum && (v.columns < 100 || v.height < Math.max(64, height)))
                return false;
            if (!spectrum && v.columns !== 0) return false;
            if (waveform && v.mode === 'hidden') return false;
            if (!waveform && v.mode !== 'hidden') return false;
            return !s.renderPending;
        }''', arg={'ch': ch, 'spectrum': spectrum, 'waveform': waveform,
                   'height': min_height}, timeout=35000)
        return view(ch)

    page.locator('#fileInput').set_input_files(str(audio))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta?.channels === 8')
    assert state()['secondaryWorkerActive'], 'Dedicated worker must initialize'
    page.locator('#channelPicker').evaluate('(x) => x.open = true')
    page.locator('#channelSelectAll').click()
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    initial = refined(2)
    assert initial['width'] > 500, initial
    assert initial['mode'] != 'hidden' and initial['columns'] > 100, initial
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

    # Zoom, scrub outside the current window and confirm the secondary image
    # catches up to the new visible time interval, not just the primary ruler.
    page.locator('#zoomIn').click()
    page.locator('#channel-spec-2').scroll_into_view_if_needed()
    zoomed = refined(2, spectrum=True, waveform=False, min_height=before_height + 100)
    assert zoomed['span'] < after_pan['span']
    page.locator('#scrubSlider').fill('2.55')
    page.locator('#scrubSlider').dispatch_event('input')
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

    assert not errors, errors
    result = {'passed': True, 'initial': initial, 'waveOnly': wave_only,
              'spectrumOnly': spectrum_only, 'resized': resized,
              'rapidPan': after_pan, 'zoom': zoomed, 'scrub': scrubbed,
              'filter': filtered, 'browser': browser.version, 'pageErrors': errors}
    (OUT / 'multichannel-sync-results.json').write_text(json.dumps(result, indent=2))
    print('MULTICHANNEL SYNCHRONIZATION PASS: preview/refinement, native detail,'
          ' resize geometry, rapid pan, zoom, seek, filter and playback selection', flush=True)
    browser.close()
