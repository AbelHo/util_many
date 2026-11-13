"""Browser regression: opt-in keyword tagging, precedence, colors, cancel and undo.

Run: python tests/audio_annotator_v2/run.py --suite import_tagging
"""
import json
from playwright.sync_api import sync_playwright
from common import SAMPLE, OUT, launch, mount


def txt(name, labels):
    return {'name': name, 'mimeType': 'text/plain', 'buffer': labels.encode('utf-8')}


def color(locator, value):
    locator.evaluate("""(node, value) => {
        node.value = value;
        node.dispatchEvent(new Event('input', {bubbles: true}));
        node.dispatchEvent(new Event('change', {bubbles: true}));
    }""", value)


with sync_playwright() as p:
    browser = launch(p)
    page = browser.new_page(viewport={'width': 1550, 'height': 1100}, accept_downloads=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    mount(page)

    def state():
        return page.evaluate('AudioAnnotatorV2.inspect()')

    def load():
        page.locator('#fileInput').set_input_files(str(SAMPLE))
        page.wait_for_function('AudioAnnotatorV2.inspect().meta !== null')

    def begin(name, labels):
        page.locator('#importInput').set_input_files(txt(name, labels))
        page.locator('#importBtn').click()
        page.locator('#importChoiceDialog[open]').wait_for()

    def count(n):
        page.wait_for_function('(count) => AudioAnnotatorV2.inspect().markerCount === count', arg=n)

    def choose(mode):
        page.locator('#importChoiceDialog [data-import-choice=' + mode + ']').click()

    def rule(term):
        return page.locator('#importSelectedRules .import-rule[data-term="' + term + '"]')

    load()
    labels = (
        '0.1\t0.1\tWhistle CLICK\n'
        '0.2\t0.2\twhistle\n'
        '0.3\t0.3\tClick train\n'
        '0.4\t0.4\tboat noise\n'
        '0.5\t0.5\tclickbait\n'
        '0.6\t0.6\tCLICK train\n'
        '0.7\t0.7\tburst pulse\n'
        '0.8\t0.8\tBurst pulse whistle\n'
    )

    begin('vocalizations.txt', labels)
    assert not page.locator('#importBatchTag').is_checked()
    assert page.locator('#importSelectedRules .import-rule').count() == 0
    assert page.locator('#importKeywordSection').is_visible()
    suggestions = page.locator('#importSuggestedRules .import-rule')
    assert suggestions.count() >= 4
    for term in ('whistle', 'click', 'burst pulse'):
        assert page.locator('#importSuggestedRules [data-term="' + term + '"]').count() == 1
        page.locator('#importSuggestedRules [data-term="' + term + '"] input[type=checkbox]').check()
    assert rule('whistle').count() == 1
    assert page.locator('#importSelectedRules .import-rule').evaluate_all(
        '(rows) => rows.map(row => row.dataset.term)') == ['whistle', 'click', 'burst pulse']

    # Native DnD, with keyboard/button fallback also available.
    rule('click').drag_to(rule('whistle'), source_position={'x': 8, 'y': 10},
                          target_position={'x': 8, 'y': 3})
    assert page.locator('#importSelectedRules .import-rule').evaluate_all(
        '(rows) => rows.map(row => row.dataset.term)') == ['click', 'whistle', 'burst pulse']
    # Higher/lower buttons remain usable without mouse drag.
    rule('whistle').locator('button[title^="Higher"]').click()
    rule('click').locator('button[title^="Higher"]').click()
    assert page.locator('#importSelectedRules .import-rule').first.get_attribute('data-term') == 'click'

    page.locator('#importBatchTag').check()
    page.locator('#importBatchTagName').fill('FileAll')
    color(page.locator('#importBatchTagColor'), '#123456')
    # Validate without closing, then correct the invalid tag key.
    page.locator('#importBatchTagName').fill('')
    choose('stack')
    assert page.locator('#importChoiceDialog[open]').count() == 1
    assert page.locator('#importChoiceError').is_visible()
    page.locator('#importBatchTagName').fill('FileAll')
    choose('stack')
    count(8)
    markers = state()['markers']
    tagged = {m['label']: m['tag'] for m in markers}
    assert tagged['Whistle CLICK'] == 'click', tagged
    assert tagged['whistle'] == 'whistle'
    assert tagged['CLICK train'] == 'click'
    assert tagged['burst pulse'] == 'burst pulse'
    assert tagged['boat noise'] == 'FileAll'
    assert tagged['clickbait'] == 'FileAll'  # Whole word, not a substring.
    assert {t['key']: t['color'] for t in state()['tags']}['FileAll'] == '#123456'
    assert state()['sources'][0]['mode'] == 'stack'
    assert page.locator('#plotStack > .label-track').count() == 1

    page.locator('#undoBtn').click()
    count(0)
    assert state()['tags'] == [] and state()['sources'] == []
    page.locator('#redoBtn').click()
    count(8)

    # Empty selections do not silently tag imported labels.
    begin('plain.txt', '0.9\t0.9\tDo not tag this\n')
    choose('merge')
    count(9)
    assert state()['markers'][-1]['tag'] == ''

    # A tagged JSON file hides suggestions, but allows explicit file-wide override.
    with page.expect_download() as download:
        page.locator('#exportJson').click()
    full_json = download.value.path().read_bytes()
    page.locator('#importInput').set_input_files({
        'name': 'roundtrip.json', 'mimeType': 'application/json', 'buffer': full_json
    })
    page.locator('#importBtn').click()
    page.locator('#importChoiceDialog[open]').wait_for()
    assert page.locator('#importKeywordSection').is_hidden()
    page.locator('#importBatchTag').check()
    page.locator('#importBatchTagName').fill('BatchAll')
    color(page.locator('#importBatchTagColor'), '#abcdef')
    choose('replace')
    count(9)
    assert all(m['tag'] == 'BatchAll' for m in state()['markers'])
    assert {t['key']: t['color'] for t in state()['tags']} == {'BatchAll': '#abcdef'}

    # Cancelling the same dialog makes no changes and does not add history.
    old = state()
    begin('cancel.txt', labels)
    choose('cancel')
    page.wait_for_function("() => !document.getElementById('importChoiceDialog').open")
    assert state()['markerCount'] == old['markerCount']
    assert state()['undo'] == old['undo']
    assert state()['tags'] == old['tags']
    assert not errors, errors
    (OUT / 'import-tagging-results.json').write_text(json.dumps({
        'passed': True, 'markers': state()['markerCount'], 'tags': state()['tags'],
        'errors': errors, 'browser': browser.version,
    }, indent=2))
    print('IMPORT TAGGING PASS: suggestions, counts, drag precedence, colors,'
          ' no-op defaults, batch override, stack/replace, undo/redo, cancel')
    browser.close()
