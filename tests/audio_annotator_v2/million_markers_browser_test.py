"""Exercise a full one-million-label Audacity import through the browser UI.

Run from the repository root:
  python tests/audio_annotator_v2/run.py --suite million_markers_browser
"""
import json
import time

from playwright.sync_api import sync_playwright

from common import OUT, SAMPLE, launch, mount


COUNT = 1_000_000
PAGE_TIMEOUT_MS = 180_000


def make_labels(count):
    """Include point, interval and spectral labels with mixed line endings."""
    rows = []
    for i in range(count):
        start = (i % 300) / 100
        end = start if i % 2 == 0 else min(start + .005, 2.999)
        label = f"click_{i} 🐬" if i % 1000 == 0 else f"click_{i}"
        newline = '\r\n' if i % 2 else '\n'
        rows.append(f'{start:.2f}\t{end:.3f}\t{label}{newline}')
        if i % 97 == 0:
            rows.append(f'\\\t1200\t1800{newline}')
    return ''.join(rows)


with sync_playwright() as p:
    browser = launch(p)
    page = browser.new_page(viewport={'width': 1500, 'height': 1000})
    page.set_default_timeout(PAGE_TIMEOUT_MS)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    mount(page)
    page.locator('#fileInput').set_input_files(str(SAMPLE))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta !== null', timeout=60_000)

    labels = make_labels(COUNT)
    encoded = labels.encode('utf-8')
    started = time.monotonic()
    page.locator('#importMode').select_option('replace')
    page.locator('#importInput').set_input_files({
        'name': 'million-mixed.labels.txt',
        'mimeType': 'text/plain',
        'buffer': encoded,
    })
    page.locator('#importBtn').click()
    page.wait_for_function(
        '(expected) => AudioAnnotatorV2.inspect().markerCount === expected',
        arg=COUNT,
    )
    elapsed = round(time.monotonic() - started, 3)
    state = page.evaluate('AudioAnnotatorV2.inspect()')
    assert state['markerCount'] == COUNT
    assert state['undo'] == 1
    assert state['markersTruncated'] is True
    assert page.locator('#markerCount').inner_text().startswith('1,000,000 markers')
    visible = state['markers']
    assert any(marker['type'] == 'point' for marker in visible)
    assert any(marker['type'] == 'time_range' for marker in visible)
    assert any(marker.get('freqMin') == 1200 and marker.get('freqMax') == 1800 for marker in visible)
    assert any('🐬' in marker['label'] for marker in visible)

    page.locator('#undoBtn').click()
    page.wait_for_function('AudioAnnotatorV2.inspect().markerCount === 0')
    page.locator('#redoBtn').click()
    page.wait_for_function(
        '(expected) => AudioAnnotatorV2.inspect().markerCount === expected',
        arg=COUNT,
    )
    assert not errors, errors
    result = {
        'status': 'PASS',
        'markers': COUNT,
        'inputBytes': len(encoded),
        'importSeconds': elapsed,
        'types': ['point', 'time_range', 'spectral'],
        'checks': ['UTF-8 labels', 'mixed LF/CRLF', 'one-million cap',
                   'UI count/pagination', 'bulk undo/redo', 'no page errors'],
        'pageErrors': errors,
    }
    (OUT / 'million-markers-browser-results.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')
    print('MILLION MARKERS BROWSER PASS:', json.dumps(result), flush=True)
    browser.close()
