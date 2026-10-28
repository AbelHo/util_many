"""Browser regression for compact synchronized tracks and inline annotation editing.

Run: python tests/audio_annotator_v2/run.py --suite inline_edit
"""
import json
from playwright.sync_api import sync_playwright
from common import SAMPLE, OUT, launch, mount


with sync_playwright() as p:
    browser = launch(p)
    page = browser.new_page(viewport={'width': 1500, 'height': 1100}, accept_downloads=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    mount(page)

    def state():
        return page.evaluate('AudioAnnotatorV2.inspect()')

    def count(n):
        page.wait_for_function('(n) => AudioAnnotatorV2.inspect().markerCount === n', arg=n)

    def labels(name, text, mode):
        page.locator('#importMode').select_option(mode)
        page.locator('#importInput').set_input_files({
            'name': name, 'mimeType': 'text/plain', 'buffer': text.encode()
        })
        page.locator('#importBtn').click()

    def plot_double_click(canvas, at_time, dx=35, y=None):
        el = page.locator(canvas)
        el.scroll_into_view_if_needed()
        box = el.bounding_box()
        v = state()
        top = 17 if box['height'] < 90 else 23
        gx = 64 + (at_time - v['start']) / v['span'] * (box['width'] - 80)
        px = gx + dx
        py = top + (8 if y is None else y)
        page.mouse.dblclick(box['x'] + px, box['y'] + py, delay=90)
        page.locator('.annotation-inline-editor').wait_for()
        assert page.locator('.annotation-inline-editor').count() == 1

    def update(tag, label, key='save'):
        page.get_by_label('Inline tag').fill(tag)
        page.get_by_label('Inline label').fill(label)
        if key == 'save':
            page.locator('.annotation-inline-editor button').filter(has_text='Save').click()
        elif key == 'enter':
            page.get_by_label('Inline label').press('Control+Enter')
        elif key == 'cancel':
            page.locator('.annotation-inline-editor button').filter(has_text='Cancel').click()
        elif key == 'outside':
            page.locator('#renderInfo').click()
        page.locator('.annotation-inline-editor').wait_for(state='hidden')

    def marker_by_start(t):
        return next(m for m in state()['markers'] if abs(m['start'] - t) < .00001)

    def compact_heights():
        plots = page.locator('#plotStack > .plot')
        separators = page.locator('#plotStack > .plot-resizer')
        assert separators.count() == plots.count() - 1
        for bar in separators.all():
            assert abs(bar.bounding_box()['height'] - 5) < 1
        widths = plots.evaluate_all("""plots => plots.map(p => {
            const r=p.querySelector('canvas').getBoundingClientRect();
            return [r.left + 64, r.right - 16];
        })""")
        assert max(x[0] for x in widths) - min(x[0] for x in widths) < 1
        assert max(x[1] for x in widths) - min(x[1] for x in widths) < 1

    page.locator('#fileInput').set_input_files(str(SAMPLE))
    page.wait_for_function('AudioAnnotatorV2.inspect().meta !== null')
    compact_heights()
    labels('stack-one.txt', '0.5\t0.5\tFirst long descriptive label\n1.5\t1.5\tSecond plotted annotation\n', 'stack')
    count(2)
    assert page.locator('#plotStack > .label-track').count() == 1
    compact_heights()

    # Double-click the TEXT, not the vertical point-line geometry (35 px away).
    plot_double_click('#plotStack > .label-track canvas.overlay', .5)
    assert page.get_by_label('Inline label').input_value() == 'First long descriptive label'
    update('click', 'Edited on stacked plot', 'save')
    assert marker_by_start(.5)['tag'] == 'click'
    assert marker_by_start(.5)['label'] == 'Edited on stacked plot'
    assert 'Edited on stacked plot' in page.locator('#markerRows').inner_text()

    # The same marker's spectrogram overlay is independently editable.
    plot_double_click('#specOverlay', .5, 12)
    update('click', 'Edited on spectrogram', 'enter')
    assert marker_by_start(.5)['label'] == 'Edited on spectrogram'

    # Editing the overlay geometry in Point mode must not create two new markers.
    page.locator('input[name=mode][value=point]').check()
    plot_double_click('#plotStack > .label-track canvas.overlay', 1.5, 0, 28)
    assert state()['markerCount'] == 2
    update('', 'Edited from point geometry', 'save')
    assert marker_by_start(1.5)['label'] == 'Edited from point geometry'

    # Table cell editing is inline and persists through table redraw/export.
    cell = page.locator('#markerRows tr').first.locator('td.marker-description')
    cell.dblclick()
    assert page.get_by_label('Inline label').input_value() == 'Edited on spectrogram'
    update('changed-tag', 'Edited in the table', 'outside')
    assert marker_by_start(.5)['label'] == 'Edited in the table'
    assert marker_by_start(.5)['tag'] == 'changed-tag'

    # A canceled edit must not affect in-memory markers.
    page.locator('#markerRows tr').first.locator('td.marker-description').dblclick()
    update('never-saved', 'This is discarded', 'cancel')
    assert marker_by_start(.5)['label'] == 'Edited in the table'

    # Undo/redo must update the table and the exported annotation values.
    page.locator('#undoBtn').click()
    assert marker_by_start(.5)['label'] == 'Edited on spectrogram'
    page.locator('#redoBtn').click()
    assert marker_by_start(.5)['label'] == 'Edited in the table'
    with page.expect_download() as event:
        page.locator('#exportJson').click()
    exported = json.loads(event.value.path().read_text(encoding='utf-8'))
    assert next(m for m in exported['markers'] if abs(m['start'] - .5) < .00001)['label'] == 'Edited in the table'

    # Merge: waveform overlay's plotted label is also editable.
    labels('merge.txt', '2.1\t2.1\tMerge overlay label\n', 'merge')
    count(3)
    page.locator('input[name=mode][value=navigate]').check()
    plot_double_click('#waveOverlay', 2.1)
    update('merge', 'Updated waveform overlay')
    assert marker_by_start(2.1)['label'] == 'Updated waveform overlay'

    # Shrink the waveform to minimum 48px; plots must remain time-aligned.
    divider = page.locator('#plotStack > .plot-resizer').first
    divider.scroll_into_view_if_needed()
    rect = divider.bounding_box()
    page.mouse.move(rect['x'] + rect['width']/2, rect['y'] + 2)
    page.mouse.down()
    page.mouse.move(rect['x'] + rect['width']/2, rect['y'] - 500, steps=8)
    page.mouse.up()
    h = page.locator('#wavePlot').bounding_box()['height']
    assert 47.5 <= h <= 49, h
    compact_heights()
    # Even at min height, the plot has a positive drawing area and cursor remains synchronized.
    assert page.locator('#waveOverlay').evaluate("""canvas => {
        const height = canvas.getBoundingClientRect().height;
        return height >= 48 && height - 17 - 15 > 0;
    }""")
    assert not errors, errors
    (OUT/'inline-edit-results.json').write_text(json.dumps({
        'passed': True, 'markers': state()['markers'], 'pageErrors': errors,
        'browser': browser.version
    }, indent=2))
    print('INLINE EDIT PASS: plot text/geometry, stacked/spectrogram/waveform, table,'
          ' undo/redo, cancel, export, compact min height and 5px gaps')
    browser.close()
