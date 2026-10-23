// Run: node helper/audio_annotatorv2.html/pan_cache_test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../../audio_annotatorv2.html'), 'utf8');
const start = html.indexOf('    function renderViewKey()');
const end = html.indexOf('    function onWorkerEvent(', start);
assert(start > 0 && end > start);
const elements = new Map();
for (const [id, value] of Object.entries({ fftSize: '2048', dbMin: '-100', dbMax: '0', colorMap: 'ember' }))
    elements.set(id, { value, style: {}, setAttribute() {} });
const $ = id => {
    if (!elements.has(id)) elements.set(id, { style: {}, attributes: {}, setAttribute(k, v) { this.attributes[k] = v; } });
    return elements.get(id);
};
let next = 1, selectedChannel = 0, selectedScale = 'linear', paints = 0, cancellations = 0;
const timers = new Map(), frames = new Map(), calls = [];
const app = { meta: { sampleRate: 192000, duration: 2048.046 }, loadEpoch: 1, start: 100, span: 10,
    renderSerial: 0, renderTimer: 0, renderFrame: 0, refineTimer: 0, renderTarget: null,
    renderCache: [], renderCacheBytes: 0, overview: { complete: false },
    analysis: { call(type, p) {
        if (type === 'cancelRender') { cancellations++; return Promise.resolve(); }
        return new Promise(resolve => calls.push({ p, resolve }));
    } } };
const range = { min: 0, max: 96000 };
const ctx = vm.createContext({ app, $, console, clamp: (v, a, b) => Math.max(a, Math.min(b, v)),
    finite: (v, fallback) => Number.isFinite(Number(v)) ? Number(v) : fallback,
    fmt: v => String(v), channel: () => selectedChannel, currentScale: () => selectedScale,
    getDisplayFreqRange: () => range, updateFreqControls: () => range,
    geom: () => ({ w: 1000, h: 200 }), fractionHz: (v, f) => f.min + v * (f.max - f.min),
    setTimeout: fn => { const id = next++; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id),
    requestAnimationFrame: fn => { const id = next++; frames.set(id, fn); return id; },
    paintAll: () => paints++, report: error => { throw error; },
    document: { createElement: () => ({ getContext: () => ({ putImageData() {} }) }) },
    ImageData: function() {} });
vm.runInContext(html.slice(start, end), ctx);
const stats = { byteCache: 0, frameCache: 0, fftCache: 0, overviewBytes: 0 };
function cached(start = 97.5, span = 15) {
    return { start, span, viewSpan: 10, viewKey: ctx.renderViewKey(), fft: 2048, columns: 960,
        image: { width: 960, height: 200 }, wave: { byteLength: 12000 }, mode: 'exact', stats, elapsedMs: 20 };
}
function fireTimer(id = app.renderTimer) { const fn = timers.get(id); assert(fn); timers.delete(id); fn(); }
function flushFrames() { const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn()); }
async function finish(call) {
    call.resolve({ ...call.p, wave: new Float32Array(3000), pixels: new Uint8ClampedArray(4),
        columns: 960, mode: 'exact', stats, elapsedMs: 20 });
    await Promise.resolve(); await Promise.resolve();
}
async function main() {
    const initial = cached(); ctx.cacheRenderedView(initial);
    app.start = 100.25; ctx.requestRender(); flushFrames();
    assert.equal(app.lastRender, initial);
    assert.equal(app.renderPending, false);
    assert.equal(timers.size, 0); assert.equal(calls.length, 0);
    assert.match($('renderInfo').textContent, /^Cached view/);
    assert.equal(paints, 1);
    console.log('PASS a covered pan draws immediately without audio I/O');

    app.start = 102; ctx.requestRender();
    assert.equal(app.renderPending, false, 'Margin refresh must not blank the cached view');
    fireTimer();
    assert.equal(calls.length, 1);
    const job = calls[0];
    assert.equal(job.p.preview, false);
    assert.equal(job.p.start, 99.5); assert.equal(job.p.span, 15);
    assert.equal(job.p.overscan, 1.5); assert.equal(job.p.width, 1500);
    const serial = app.renderSerial;
    app.start = 103; ctx.requestRender();
    assert.equal(app.renderSerial, serial);
    assert.equal(cancellations, 0, 'Panning inside the new margin must not repeatedly cancel prefetch');
    await finish(job);
    assert(ctx.renderCovers(app.lastRender, ctx.renderViewKey()));
    assert.equal(app.renderPending, false);
    app.start = 98.5; ctx.requestRender();
    assert(app.lastRender === initial, 'Reverse pan should reuse the previous cached view');
    console.log('PASS margin refresh survives continued panning; reverse pan reuses prior data');

    const key = ctx.renderViewKey();
    selectedChannel = 1; assert.equal(ctx.cachedView(), null); selectedChannel = 0;
    selectedScale = 'log'; assert.equal(ctx.cachedView(), null); selectedScale = 'linear';
    $('fftSize').value = '4096'; assert.equal(ctx.cachedView(), null); $('fftSize').value = '2048';
    $('colorMap').value = 'gray'; assert.equal(ctx.cachedView(), null); $('colorMap').value = 'ember';
    range.min = 100; assert.equal(ctx.cachedView(), null); range.min = 0;
    app.overview.complete = true; assert.equal(ctx.cachedView(), null); app.overview.complete = false;
    app.span = 5; assert.equal(ctx.cachedView(), null); app.span = 10;
    assert.equal(ctx.renderViewKey(), key);
    app.start = 0; assert(ctx.renderCovers(cached(0, 12.5), key, .1));
    app.start = app.meta.duration - 10;
    assert(ctx.renderCovers(cached(app.meta.duration - 12.5, 12.5), key, .1));
    console.log('PASS settings/zoom changes invalidate reuse; both recording edges remain covered');

    app.start = 500; ctx.requestRender(); fireTimer();
    const stale = calls.at(-1), previous = app.lastRender;
    app.start = 1500; ctx.requestRender();
    assert.equal(cancellations, 1);
    await finish(stale);
    assert.equal(app.lastRender, previous, 'Superseded job must not overwrite a newer pan');
    app.renderCache = []; app.renderCacheBytes = 0;
    for (let i = 0; i < 10; i++) ctx.cacheRenderedView(cached(i * 10));
    assert.equal(app.renderCache.length, 6);
    for (let i = 0; i < 10; i++) ctx.cacheRenderedView({ ...cached(), image: { width: 2000, height: 1000 } });
    assert(app.renderCacheBytes <= 16 * 1048576);
    assert.equal(app.renderCacheBytes, app.renderCache.reduce((sum, r) => sum + r.cacheBytes, 0));
    console.log('PASS stale results rejected; cache stays within six entries and 16 MiB');
}
module.exports = { app, ctx, $, elements, range, timers, frames, calls, cached, fireTimer, flushFrames, finish };
if (require.main === module) main().catch(e => { console.error(e); process.exitCode = 1; });
