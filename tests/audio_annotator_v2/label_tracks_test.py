"""Browser tests: merge/replace/stack, visibility, alignment, resizing and import history.

Run: python tests/audio_annotator_v2/run.py --suite label_tracks
"""
import json
from playwright.sync_api import sync_playwright
from common import SAMPLE, OUT, launch, mount


def txt(name, labels):
    return {'name': name, 'mimeType': 'text/plain', 'buffer': labels.encode('utf-8')}


with sync_playwright() as p:
    browser = launch(p)
    page = browser.new_page(viewport={'width': 1500, 'height': 1100}, accept_downloads=True)
    page_errors = []
    page.on('pageerror', lambda error: page_errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    mount(page)

    def state():
        return page.evaluate('AudioAnnotatorV2.inspect()')

    def views():
        return page.evaluate('AudioAnnotatorV2.overlayDebug()')

    def loaded():
        page.wait_for_function('AudioAnnotatorV2.inspect().meta !== null')

    def source_count(n):
        page.wait_for_function('(n) => AudioAnnotatorV2.inspect().sources.length === n', arg=n)

    def marker_count(n):
        page.wait_for_function('(n) => AudioAnnotatorV2.inspect().markerCount === n', arg=n)

    def upload(name, labels, mode, sources, markers):
        page.locator('#importMode').select_option(mode)
        page.locator('#importInput').set_input_files(txt(name, labels))
        page.locator('#importBtn').click()
        source_count(sources)
        marker_count(markers)

    def assert_time_alignment():
        geometry = page.evaluate("""() => [...document.querySelectorAll('#plotStack > .plot')].map(p => {
            const r = p.querySelector('canvas').getBoundingClientRect();
            return { left: r.left + 64, right: r.right - 16, width: r.width };
        })""")
        assert len(geometry) >= 2
        assert max(g['left'] for g in geometry) - min(g['left'] for g in geometry) < 1.1, geometry
        assert max(g['right'] for g in geometry) - min(g['right'] for g in geometry) < 1.1, geometry

    def drag_splitter(n, distance):
        bar = page.locator('#plotStack > .plot-resizer').nth(n)
        before = page.locator('#plotStack > .plot').evaluate_all(
            '(plots) => plots.map(p => p.getBoundingClientRect().height)'
        )
        box = bar.bounding_box()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.mouse.down()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2 + distance, steps=8)
        page.mouse.up()
        after = page.locator('#plotStack > .plot').evaluate_all(
            '(plots) => plots.map(p => p.getBoundingClientRect().height)'
        )
        assert abs(after[n] - before[n] - distance) < 4, (before, after)
        assert abs(after[n + 1] - before[n + 1] + distance) < 4, (before, after)
        assert abs(sum(after) - sum(before)) < 3, (before, after)
        assert_time_alignment()

    page.locator('#fileInput').set_input_files(str(SAMPLE))
    loaded()
    assert page.locator('#importMode option[value=replace]').count() == 1
    assert page.locator('#importMode option[value=stack]').count() == 1
    assert page.locator('#plotStack > .plot-resizer').count() == 1
    assert_time_alignment()

    # Stacked labels do not overlay waveform, but do overlay spectrogram.
    upload('a.txt', '0.2\t0.2\tFirst\n0.4\t0.5\tSecond\n', 'stack', 1, 2)
    upload('b.txt', '0.3\t0.3\tThird\n1.5\t1.7\tFourth\n', 'stack', 2, 4)
    assert page.locator('#plotStack > .label-track').count() == 2
    assert page.locator('#plotStack > .plot-resizer').count() == 3
    assert page.locator('#importSourceControls input[type=checkbox]').count() == 2
    assert [s['mode'] for s in state()['sources']] == ['stack', 'stack']
    assert views()['waveform'] == 0 and views()['spectrogram'] == 4
    assert [t['count'] for t in views()['tracks']] == [2, 2]
    assert_time_alignment()

    first = page.locator('#importSourceControls input').first
    first.uncheck()
    assert views()['spectrogram'] == 2 and [t['count'] for t in views()['tracks']] == [0, 2]
    assert state()['markerCount'] == 4
    first.check()
    assert views()['spectrogram'] == 4
    page.locator('#showAnnotations').uncheck()
    assert state()['markerCount'] == 4
    page.locator('#showAnnotations').check()
    page.locator('#showLabelText').uncheck()
    page.locator('#showLabelText').check()

    drag_splitter(1, 22)    # label A | label B
    drag_splitter(0, 18)    # waveform | label A
    drag_splitter(2, 22)    # label B | spectrogram
    page.locator('#plotStack > .plot-resizer').first.focus()
    h = page.locator('#wavePlot').evaluate('(p) => p.getBoundingClientRect().height')
    page.keyboard.press('ArrowDown')
    assert page.locator('#wavePlot').evaluate('(p) => p.getBoundingClientRect().height') > h

    page.locator('input[name=mode][value=navigate]').check()
    canvas = page.locator('#plotStack > .label-track canvas.overlay').first
    box = canvas.bounding_box()
    canvas.click(position={'x': 64 + .88 * (box['width'] - 80),
                           'y': 23 + .5 * (box['height'] - 51)})
    assert state()['cursor'] > 2.2
    assert_time_alignment()

    upload('merged.txt', '0.6\t0.6\tMerged\n', 'merge', 3, 5)
    assert page.locator('#plotStack > .label-track').count() == 2
    assert views()['waveform'] == 1 and views()['spectrogram'] == 5
    assert page.locator('#importSourceControls input').count() == 3

    with page.expect_download() as event:
        page.locator('#exportJson').click()
    exported = json.loads(event.value.path().read_text(encoding='utf-8'))
    assert len(exported['sources']) == 3
    assert {m['sourceId'] for m in exported['markers']} == {s['id'] for s in exported['sources']}

    upload('replacement.txt', '0.9\t0.9\tReplacement\n', 'replace', 1, 1)
    assert page.locator('#plotStack > .label-track').count() == 0
    assert views()['waveform'] == views()['spectrogram'] == 1
    page.locator('#undoBtn').click()
    source_count(3)
    marker_count(5)
    assert page.locator('#plotStack > .label-track').count() == 2
    assert [t['count'] for t in views()['tracks']] == [2, 2]
    page.locator('#redoBtn').click()
    source_count(1)
    marker_count(1)
    assert page.locator('#plotStack > .label-track').count() == 0

    page.locator('#importMode').select_option('stack')
    page.locator('#importInput').set_input_files(txt(
        'invalid.txt', '0.2\t0.2\tValid\n999\t999\tInvalid\n'))
    page.locator('#importBtn').click()
    page.wait_for_function("() => document.getElementById('status').textContent.includes('outside')")
    source_count(1)
    marker_count(1)
    assert page.locator('#plotStack > .label-track').count() == 0

    # Per-file choice is required for each dropped file, not just the first.
    page.evaluate("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(['1.1\t1.1\tStack from drop\n'], 'dropped-stack.txt', {type: 'text/plain'}));
        dt.items.add(new File(['1.2\t1.2\tMerge from drop\n'], 'dropped-merge.txt', {type: 'text/plain'}));
        document.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
    }""")
    page.locator('#importChoiceDialog[open]').wait_for()
    page.locator('[data-import-choice=stack]').click()
    page.wait_for_function("""() => document.querySelector('#importChoiceDialog[open] #importChoiceTitle')?.textContent.includes('dropped-merge.txt')""")
    page.locator('[data-import-choice=merge]').click()
    source_count(3)
    marker_count(3)
    assert page.locator('#plotStack > .label-track').count() == 1
    assert views()['waveform'] == 2 and views()['spectrogram'] == 3
    assert [s['filename'] for s in state()['sources']] == [
        'replacement.txt', 'dropped-stack.txt', 'dropped-merge.txt'
    ]

    assert not page_errors, page_errors
    (OUT / 'label-tracks-results.json').write_text(json.dumps({
        'passed': True, 'sources': state()['sources'], 'views': views(),
        'pageErrors': page_errors, 'browser': browser.version
    }, indent=2))
    print('LABEL TRACKS PASS: merge/replace/stack, per-file visibility, alignment,'
          ' resize, undo/redo, atomic failure, provenance, multi-file drop')
    browser.close()
