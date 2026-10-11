"""Audacity standard/extended TXT interoperability and browser UI regression checks.

Run from the repository root:
  python tests/audio_annotator_v2/run.py --suite audacity_labels
"""
import json
from playwright.sync_api import sync_playwright
from common import SAMPLE, OUT, launch, mount

results = []
with sync_playwright() as p:
    browser = launch(p)
    page = browser.new_page(viewport={'width': 1600, 'height': 1100}, accept_downloads=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    mount(page)

    def state():
        return page.evaluate('AudioAnnotatorV2.inspect()')

    def count(n):
        page.wait_for_function('(n) => AudioAnnotatorV2.inspect().markers.length === n', arg=n)

    def upload(text, name='annotations.labels.txt', mode='replace'):
        page.locator('#importMode').select_option(mode)
        page.locator('#importInput').set_input_files({
            'name': name, 'mimeType': 'text/plain',
            'buffer': text.encode('utf-8') if isinstance(text, str) else text
        })
        page.locator('#importBtn').click()

    def export(style='extended'):
        page.locator('#audacityLabelStyle').select_option(style)
        with page.expect_download() as event:
            page.locator('#exportTxt').click()
        download = event.value
        path = OUT / ('audacity-' + style + '.txt')
        download.save_as(path)
        assert download.suggested_filename.endswith('.labels.txt')
        return path.read_text(encoding='utf-8')

    def canonical():
        return sorted(
            [{key: m[key] for key in ('type', 'start', 'end', 'frequency', 'freqMin', 'freqMax', 'label')}
             for m in state()['markers']],
            key=lambda marker: (marker['start'], marker['end'])
        )

    page.locator('#fileInput').set_input_files(str(SAMPLE))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta !== null')
    metadata = state()['meta']
    duration, nyquist = metadata['duration'], metadata['sampleRate'] / 2
    assert duration > 0 and nyquist > 0
    t = [float(f'{duration * f:.9f}') for f in (.05, .1, .2, .3, .4, .5, .6, .7, .8)]
    h = lambda f: float(f'{nyquist * f:.8f}')
    sample = (
        f'{t[0]}\t{t[0]}\tClick 🐬\r\n'
        f'\\\t{h(.6)}\t{h(.6)}\r\n'
        f'{t[1]}\t{t[2]}\tHigh only\r\n'
        f'\\\t-1\t{h(.4)}\r\n'
        f'{t[3]}\t{t[4]}\tLow only\r\n'
        f'\\\t{h(.15)}\t-1\r\n'
        f'{t[5]}\t{t[5]}\tPoint with spectral band\r\n'
        f'\\\t{h(.1)}\t{h(.3)}\r\n'
        f'{t[6]}\t{t[7]}\tEqual frequency boundaries\r\n'
        f'\\\t{h(.25)}\t{h(.25)}\r\n'
        f'{t[8]}\tLegacy point\r\n'
    )
    upload('\ufeff' + sample)
    count(6)
    markers = canonical()
    assert markers[0]['type'] == 'point' and markers[0]['frequency'] == h(.6)
    assert markers[1]['freqMin'] is None and markers[1]['freqMax'] == h(.4)
    assert markers[2]['freqMin'] == h(.15) and markers[2]['freqMax'] is None
    assert markers[3]['type'] == 'point' and markers[3]['freqMin'] == h(.1)
    assert markers[4]['freqMin'] == markers[4]['freqMax'] == h(.25)
    assert markers[5]['type'] == 'point'
    results.append('file picker: BOM/CRLF, Unicode, legacy points, full/partial/equal-frequency labels')

    extended = export()
    assert extended.count('\\\t') == 5 and 'Click 🐬' in extended
    upload(extended)
    count(6)
    assert canonical() == markers
    results.append('extended export, download and exact spectral TXT re-import')

    standard = export('standard')
    assert '\\\t' not in standard
    upload(standard)
    count(6)
    assert all(m['freqMin'] is None and m['freqMax'] is None and m['frequency'] is None for m in canonical())
    results.append('standard export omits frequencies with confirmation')

    upload(extended)
    count(6)
    page.locator('#undoBtn').click()
    count(6)
    assert all(m['frequency'] is None for m in canonical())
    page.locator('#redoBtn').click()
    count(6)
    assert canonical() == markers
    results.append('replace is one undoable transaction')

    # Atomic failure: first record is valid, second falls beyond this WAV.
    snapshot = canonical()
    upload(f'{t[0]}\t{t[0]}\tOK\n{duration + 100}\t{duration + 101}\tInvalid\n')
    page.wait_for_function("document.getElementById('status').textContent.includes('outside')")
    assert canonical() == snapshot
    upload(b'1\t1\tUTF8\xffbroken\n')
    page.wait_for_function("document.getElementById('status').textContent.includes('UTF') or document.getElementById('status').textContent.includes('encoded')")
    assert canonical() == snapshot
    results.append('invalid TXT, out-of-bounds times and invalid UTF-8 leave state untouched')

    # Drop a TXT annotation alongside previously loaded audio.
    page.evaluate("""(txt) => {
        const transfer = new DataTransfer();
        transfer.items.add(new File([txt], 'dropped.TXT', {type: 'text/plain'}));
        document.dispatchEvent(new DragEvent('drop', {
            bubbles: true, cancelable: true, dataTransfer: transfer
        }));
    }""", extended)
    count(12)
    page.locator('#undoBtn').click()
    count(6)
    results.append('drag-and-drop merges TXT, undo rolls back only the dropped batch')

    # The exported TXT copy, unlike JSON, cannot represent multiline labels.
    page.locator('#markerRows tr').first.locator('button').first.click()
    page.locator('#editLabel').fill('Two\nlines\tand tabs')
    page.locator('#saveMarker').click()
    flattened = export()
    assert 'Two lines and tabs' in flattened
    assert 'Two\nlines' not in flattened
    assert any(m['label'] == 'Two\nlines\tand tabs' for m in canonical())
    results.append('lossy TXT export explicitly confirms text flattening without mutating originals')

    assert not errors, errors
    (OUT / 'audacity-labels-results.json').write_text(
        json.dumps({'passed': results, 'pageErrors': errors}, indent=2), encoding='utf-8')
    print('AUDACITY TXT PASS:', '; '.join(results))
    browser.close()
