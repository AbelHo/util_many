// Dependency-free regression checks for the single-file annotator.
// Run: node helper/audio_annotatorv2.html/large_labels_test.cjs [Audacity TXT path]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { randomUUID } = require('node:crypto');
const { performance } = require('node:perf_hooks');
const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'audio_annotatorv2.html'), 'utf8');
for (const m of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)) new vm.Script(m[1]);
function section(start, end) {
    const a = html.indexOf(start), b = html.indexOf(end, a);
    assert(a >= 0 && b > a, `Missing source section: ${start}`);
    return html.slice(a, b);
}
const elements = new Map();
const app = { meta: { duration: 2048.046, sampleRate: 192000 }, file: { name: 'test.wav', size: 1 },
    loadEpoch: 1, importSerial: 0, importBusy: false, markers: new Map(), tags: new Map(),
    markerVersion: 0, markerIndex: null, overlayLayers: {}, undo: [], redo: [], historyBytes: 0,
    selected: null, start: 0, span: 2048.046, tableSerial: 0 };
const context = vm.createContext({ app, Map, Float64Array, Uint32Array, TextDecoder, Blob,
    performance, setTimeout, clearTimeout, console, uid: randomUUID,
    MAX_IMPORT_BYTES: 256 * 1048576, MAX_MARKERS: 1000000, HISTORY_BYTES: 256 * 1048576,
    clamp: (v, a, b) => Math.max(a, Math.min(b, v)),
    tX: (time, g) => g.left + (time - app.start) / app.span * g.w,
    $: id => { if (!elements.has(id)) elements.set(id, {}); return elements.get(id); },
    status() {}, refreshAnnotations() {}, renderMarkerTable() {}, confirm: () => true });
vm.runInContext([
    section('    function invalidateMarkers(', '    function styleFor('),
    section('    function cleanText(', '    function normalizeTag('),
    section('    function writableAnnotationMaps(', '    function addMarker('),
    section('    function audacityBounds(', '    const csvCell'),
    section('    async function importText(', '    async function importFile('),
    section('    function nearestMarker(', '    function gestureMarker(')
].join('\n'), context);
const api = vm.runInContext('({parseAudacityLabels,importText,markerIndex,markerDensity,visibleMarkerCount,forEachVisibleMarker,invalidateMarkers,transact,history,exportAudacityLabels,nearestMarker})', context);
function install(markers) {
    app.markers = new Map(markers.map((m, i) => [String(i), { id: String(i), ...m }]));
    api.invalidateMarkers();
    return api.markerIndex();
}
async function main() {
    // Compare counts and binning with an independent brute-force overlap oracle.
    const markers = [{ start: 0, end: 0 }, { start: 10, end: 10 }, { start: 0, end: 10 }];
    for (let i = 0; i < 1500; i++) markers.push({ start: (i * 37 % 1000) / 100, end: (i * 37 % 1000) / 100 + (i % 4) / 100 });
    const index = install(markers);
    for (const [start, end] of [[0, 10], [2, 4], [0, .01], [9.99, 10], [10, 11], [20, 30]]) {
        const expected = markers.filter(m => m.start <= end && m.end >= start);
        assert.equal(api.visibleMarkerCount(index, start, end), expected.length);
        const found = [];
        api.forEachVisibleMarker(start, end, m => { found.push(m); });
        assert.equal(found.length, expected.length);
        const width = 101, bins = api.markerDensity(index, start, end, width);
        for (let x = 0; x < width; x++) {
            const left = start + (end - start) * x / width, right = start + (end - start) * (x + 1) / width;
            const n = markers.filter(m => (x === width - 1 ? m.start <= right : m.start < right) && m.end >= left).length;
            assert.equal(bins[x], n, `bin ${x} at ${start}–${end}`);
        }
    }
    console.log('PASS exact counts, bin boundaries, long ranges and interval queries');

    // UTF-8 and CRLF splits, optional frequency continuations, and final no-newline.
    const rows = await api.parseAudacityLabels(new Blob(['\ufeff1\t1\t海豚\r\n\\\t1000\t2000\r2\t3\tcall\n4\t4\tend']));
    assert.equal(rows.length, 3);
    assert.equal(rows[0].label, '海豚');
    assert.equal(rows[0].freqMin, 1000);
    assert.equal(rows[2].label, 'end');
    const padding = '\n'.repeat(256 * 1024 - 1);
    assert.equal((await api.parseAudacityLabels(new Blob([padding, '\r\n1\t1\tx']))).length, 1);
    const utf8Padding = '\n'.repeat(256 * 1024 - 5);
    assert.equal((await api.parseAudacityLabels(new Blob([utf8Padding, '1\t1\t海豚'])))[0].label, '海豚');
    await assert.rejects(api.parseAudacityLabels(new Blob([Uint8Array.from([0xff])])), /encoded data/);
    console.log('PASS streaming UTF-8, CRLF, BOM and spectral continuations');

    const oldMap = app.markers;
    await assert.rejects(api.importText('1\t1\tok\n2\tbad\tx', 'txt', 'replace', false), /invalid end/);
    assert.equal(app.markers, oldMap);
    const cancel = api.importText(new Blob(['1\t1\tx\n'.repeat(30000)]), 'txt', 'replace', false);
    setTimeout(() => app.importSerial++, 0);
    await assert.rejects(cancel, /cancelled/);
    assert.equal(app.markers, oldMap);
    console.log('PASS invalid/cancelled import leaves annotations unchanged');

    const sample = process.argv[2] || path.join(root, 'sample/combined_impulse__audacity.txt');
    const text = fs.existsSync(sample) ? fs.readFileSync(sample, 'utf8') :
        Array.from({ length: 135200 }, (_, i) => `${i / 100}\t${i / 100}\t${i + 1}`).join('\n');
    const expected = text.split(/\r\n|\r|\n/).filter(line => line && !line.startsWith('\\')).length;
    const started = performance.now();
    await api.importText(new Blob([text]), 'txt', 'replace', false);
    assert.equal(app.markers.size, expected);
    const imported = app.markers, build = performance.now(), large = api.markerIndex(), indexed = performance.now();
    const bins = api.markerDensity(large, 0, app.meta.duration, 1600);
    const densityMs = performance.now() - indexed;
    assert.equal(api.visibleMarkerCount(large, 0, app.meta.duration), expected);
    // This fixture contains points, so every label must appear in exactly one bin.
    assert.equal(bins.reduce((a, b) => a + b, 0), expected);
    assert(bins.slice(800).some(n => n > 0), 'Late events must not disappear behind a first-N cap');
    const exportText = api.exportAudacityLabels(large.items, true, false, true);
    const roundtrip = await api.parseAudacityLabels(new Blob([exportText]));
    assert.equal(roundtrip.length, expected);
    for (const i of [0, 4999, 5000, expected - 1]) {
        assert.equal(roundtrip[i].start, large.items[i].start);
        assert.equal(roundtrip[i].label, large.items[i].label);
    }
    const before = large.items[expected - 1];
    const g = { left: 0, top: 0, w: 1000, h: 200 };
    elements.set('showAnnotations', { checked: true });
    assert.equal(api.nearestMarker({ time: before.start, x: before.start / app.span * g.w, y: 100, g }, false), null,
        'A dense aggregate must never select or Shift-delete a hidden individual');
    app.start = before.start - .001; app.span = .002;
    assert.equal(api.nearestMarker({ time: before.start, x: 500, y: 100, g }, false).id, before.id);
    elements.get('showAnnotations').checked = false;
    assert.equal(api.nearestMarker({ time: before.start, x: 500, y: 100, g }, false), null);
    console.log('PASS aggregate/hidden hit testing disabled; individual selection restored after zoom');
    api.transact({ markers: [{ id: before.id, before, after: { ...before, label: 'edited last marker' } }] });
    assert.equal(api.markerIndex(), large, 'A label edit must reuse the time index');
    assert.equal(api.markerIndex().items[expected - 1].label, 'edited last marker');
    assert.equal(imported.get(before.id).label, before.label, 'Bulk undo snapshot must stay immutable');
    api.history(false);
    assert.equal(api.markerIndex().items[expected - 1].label, before.label);
    api.history(false);
    assert.equal(app.markers, oldMap);
    api.history(true);
    assert.equal(app.markers.size, expected);
    console.log(`PASS ${expected.toLocaleString()} labels, full density, TXT round-trip, last-marker edit and bulk undo/redo`);
    console.log(JSON.stringify({ importMs: Math.round(build - started), indexMs: Math.round(indexed - build), densityMs: +densityMs.toFixed(1) }));
}
main().catch(e => { console.error(e); process.exitCode = 1; });
