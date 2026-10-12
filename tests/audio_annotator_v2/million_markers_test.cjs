// Run: node --max-old-space-size=4096 tests/audio_annotator_v2/million_markers_test.cjs
// No npm packages. Extracts the actual app functions; validates million-label
// parsing, interval-index queries, import undo/redo and immutable snapshots.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', '..', 'audio_annotatorv2.html'), 'utf8');
const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map(x => x[1]);
assert.equal(scripts.length, 2, 'Expected worker and main inline scripts');
for (const script of scripts) new vm.Script(script);
const main = scripts[1];
function section(begin, end) {
    const start = main.indexOf(begin), finish = main.indexOf(end, start + begin.length);
    assert.ok(start >= 0 && finish > start, 'Missing section ' + begin);
    return main.slice(start, finish);
}
assert.match(main, /MAX_MARKERS = 1000000/);
assert.match(main, /MAX_IMPORT_BYTES = 256 \* 1048576/);

const app = { meta: { duration: 2000000, sampleRate: 48000 }, loadEpoch: 0,
    markers: new Map(), tags: new Map(), selected: null, undo: [], redo: [],
    historyBytes: 0, dirty: false, importBusy: false,
    markerVersion: 0, markerIndex: null, tableCache: null,
    overlayLayers: { wave: null, spec: null } };
let counter = 0;
const env = {
    app, MAX_MARKERS: 1000000, MAX_IMPORT_BYTES: 256 * 1048576,
    HISTORY_BYTES: 256 * 1048576, Float64Array, Map, Set, Promise,
    setTimeout, clearTimeout, Math, Number, Date, String, Error,
    uid: () => 'import-' + (++counter),
    clamp: (v, a, b) => Math.max(a, Math.min(b, v)),
    status: () => {}, refreshAnnotations: () => {},
    renderMarkerTable: () => {}, $: () => ({ value: '', checked: false })
};
vm.createContext(env);
vm.runInContext(
    section('    function cleanText(', '    function normalizeTag(') +
    section('    const yieldUI =', '    function exportAudacityLabels(') +
    section('    function invalidateMarkers()', '    function styleFor(') +
    section('    function writableAnnotationMaps()', '    function addMarker(') +
    '\nthis.tests = { parseAudacityLabels, markerIndex, forEachVisibleMarker, transactSnapshot, transact, history };',
    env
);
const { parseAudacityLabels, forEachVisibleMarker, transactSnapshot, transact, history } = env.tests;

(async () => {
    const mixed = await parseAudacityLabels('\uFEFF0\t0\tclick\r\n\\\t100\t100\r\n1\t2\twhistle\n\\\t-1\t300\n3\tlegacy\r4\t4\tend');
    assert.equal(mixed.length, 4);
    assert.equal(mixed[0].frequency, 100);
    assert.equal(mixed[1].freqMax, 300);
    assert.equal(mixed[2].label, 'legacy');
    await assert.rejects(parseAudacityLabels('oops\t0\tinvalid'), /invalid start time/);
    await assert.rejects(parseAudacityLabels('\\\t1\t2'), /orphan/);
    await assert.rejects(parseAudacityLabels('0\t0\tlabel\textra'), /labels cannot contain tabs/);

    // Build in 10k-row blocks, avoiding a temporary million-entry input array.
    const blocks = [], chunkSize = 10000, total = 1000000;
    for (let begin = 0; begin < total; begin += chunkSize) {
        const rows = [];
        for (let i = begin; i < begin + chunkSize; i++)
            rows.push((i / 10) + '\t' + (i / 10) + '\tclick_' + i);
        blocks.push(rows.join('\n') + '\n');
    }
    const started = Date.now();
    const parsed = await parseAudacityLabels(blocks.join(''));
    assert.equal(parsed.length, total);
    assert.equal(parsed[0].label, 'click_0');
    assert.equal(parsed.at(-1).label, 'click_999999');
    assert.notEqual(parsed[0].id, parsed.at(-1).id);
    console.log('PASS 1,000,000 Audacity TXT labels in', Date.now() - started, 'ms');

    // Boundary enforcement without paying for an additional 1m-row parse.
    env.MAX_MARKERS = 3;
    await assert.rejects(parseAudacityLabels('0\t0\ta\n1\t1\tb\n2\t2\tc\n3\t3\td'), /annotation limit/);
    env.MAX_MARKERS = total;

    const byId = new Map(parsed.map(m => [m.id, m]));
    app.markers = byId;
    env.tests.markerIndex();
    const hits = [];
    forEachVisibleMarker(500, 500.2, m => hits.push(m.start));
    assert.deepEqual(hits, [500, 500.1, 500.2]);
    // A range starting far before the window still overlaps and must be found.
    const long = { ...parsed[0], id: 'long', start: 0, end: 1000 };
    byId.set(long.id, long);
    env.tests.invalidateMarkers?.(); // see manual invalidation below
    app.markerIndex = null;
    assert.ok((() => { let found = false; forEachVisibleMarker(900, 901, m => { if (m.id === 'long') found = true; }); return found; })());

    const original = new Map([['old', { id: 'old' }]]);
    app.markers = original; app.markerIndex = null;
    transactSnapshot(byId, new Map());
    assert.equal(app.markers.size, total + 1);
    history(false); assert.equal(app.markers.size, 1);
    history(true); assert.equal(app.markers.size, total + 1);
    transact({ markers: [{ id: 'extra', before: null, after: { id: 'extra' } }] });
    assert.equal(byId.has('extra'), false, 'An edit must not mutate a saved bulk snapshot');
    history(false); history(false);
    assert.equal(app.markers.size, 1);
    history(true); history(true);
    assert.equal(app.markers.size, total + 2);
    console.log('PASS indexed overlap search, snapshot undo/redo, copy-on-write edits');
})().catch(e => { console.error(e); process.exitCode = 1; });
