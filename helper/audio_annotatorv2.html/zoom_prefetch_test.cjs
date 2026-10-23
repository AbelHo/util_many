// Run: node helper/audio_annotatorv2.html/zoom_prefetch_test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { app, ctx, $, timers, timerDelays, frames, calls, cached, fireTimer, finish, cancellations } = require('./pan_cache_test.cjs');
const html = fs.readFileSync(path.join(__dirname, '../../audio_annotatorv2.html'), 'utf8');
vm.runInContext(html.slice(html.indexOf('    function setView('), html.indexOf('    function renderViewKey()')), ctx);

function reset() {
    ctx.cancelZoomPrefetch(); timers.clear(); frames.clear(); calls.length = 0;
    Object.assign(app, { start: 100, span: 10, renderPending: false, renderTarget: null,
        renderTimer: 0, refineTimer: 0, renderFrame: 0, renderCache: [], renderCacheBytes: 0,
        zoomHint: { factor: .5, fraction: .2 }, playing: false, importBusy: false, gesture: null });
    app.overview.active = false; ctx.document.hidden = false; $('fftSize').value = '2048';
    app.lastRender = cached(); ctx.cacheRenderedView(app.lastRender);
    $('renderInfo').textContent = 'Current view';
}
function begin() {
    ctx.scheduleZoomPrefetch();
    assert.equal(timerDelays.get(app.prefetchTimer), 600);
    assert.equal(calls.length, 0, 'Prediction must wait for the idle delay');
    fireTimer(app.prefetchTimer);
    assert.equal(calls.length, 1);
    return calls[0];
}
async function main() {
    reset();
    const visible = app.lastRender, job = begin();
    assert.equal(job.p.preview, false);
    assert.equal(job.p.start, 99.75); assert.equal(job.p.span, 7.5);
    assert.equal(job.p.overscan, 1.5); assert.equal(job.p.width, 1500);
    await finish(job);
    const prediction = app.renderCache.at(-1);
    assert.equal(prediction.viewSpan, 5); assert.equal(prediction.speculative, true);
    assert.equal(app.lastRender, visible); assert.equal(app.renderPending, false);
    assert.equal($('renderInfo').textContent, 'Current view');
    assert.equal(app.prefetchTarget, null); assert.equal(timers.size, 0, 'No recursive prediction chain');
    ctx.scheduleZoomPrefetch(); fireTimer(app.prefetchTimer);
    assert.equal(calls.length, 1, 'Already prepared targets must not run again');
    ctx.zoom(.5, 102);
    assert.equal(app.start, 101); assert.equal(app.span, 5);
    assert.equal(app.lastRender, prediction); assert.equal(prediction.speculative, false);
    assert.equal(app.renderPending, false); assert.equal(app.renderTimer, 0);
    assert.match($('renderInfo').textContent, /^Cached view/);
    console.log('PASS one delayed prediction preserves anchor, uses full detail and serves the next zoom immediately');

    reset(); const stale = begin(), before = app.renderCache.slice(), oldVisible = app.lastRender;
    const priorCancellations = cancellations();
    ctx.zoom(2);
    assert.equal(cancellations(), priorCancellations + 1, 'Navigation must cancel active speculation immediately');
    assert.equal(app.prefetchTarget, null);
    await finish(stale);
    assert.deepEqual(app.renderCache, before); assert.equal(app.lastRender, oldVisible);
    fireTimer(); const quick = calls.at(-1);
    assert.equal(quick.p.preview, true); assert.equal(quick.p.span, 20);
    await finish(quick);
    fireTimer(app.refineTimer); const full = calls.at(-1);
    assert.equal(app.refineTimer, 0); assert.equal(full.p.preview, false);
    await finish(full);
    assert.equal(app.lastRender.viewSpan, 20); assert.equal(app.renderPending, false);
    assert(app.prefetchTimer, 'Only the settled foreground result may schedule new speculation');
    console.log('PASS foreground navigation cancels speculation, rejects its stale result and finishes quick/full rendering');

    for (const busy of ['playing', 'importBusy', 'gesture', 'renderPending', 'renderTarget', 'renderTimer', 'refineTimer']) {
        reset(); app[busy] = true; ctx.scheduleZoomPrefetch();
        assert.equal(app.prefetchTimer, 0, busy + ' must suppress prediction');
    }
    reset(); ctx.document.hidden = true; ctx.scheduleZoomPrefetch(); assert.equal(app.prefetchTimer, 0);
    reset(); app.overview.active = true; ctx.scheduleZoomPrefetch(); assert.equal(app.prefetchTimer, 0);
    reset(); ctx.scheduleZoomPrefetch(); app.playing = true; fireTimer(app.prefetchTimer);
    assert.equal(calls.length, 0, 'Idle conditions must be rechecked after the delay');
    for (const changed of ['file', 'settings']) {
        reset(); const pending = begin();
        if (changed === 'file') app.loadEpoch++; else $('fftSize').value = '4096';
        await finish(pending);
        assert.equal(app.renderCache.length, 1, changed + ' change must reject the result');
    }
    reset(); const failure = begin(); failure.reject(Error('Optional read failed'));
    await new Promise(setImmediate);
    assert.equal(app.prefetchTarget, null); assert.equal($('renderInfo').textContent, 'Current view');
    console.log('PASS busy/hidden suppression, stale file/settings guards and optional failure isolation');

    reset(); app.start = 0; app.zoomHint = { factor: 2, fraction: .75 };
    assert.equal(ctx.predictedZoom().start, 0);
    app.start = app.meta.duration - 10;
    assert.equal(ctx.predictedZoom().start + ctx.predictedZoom().span, app.meta.duration);
    app.span = app.meta.duration; assert.equal(ctx.predictedZoom(), null);
    app.span = 4 / app.meta.sampleRate; app.zoomHint.factor = .5; assert.equal(ctx.predictedZoom(), null);
    reset(); ctx.zoom(1.2, 103);
    assert(Math.abs(ctx.predictedZoom().span - 14.4) < 1e-12);
    assert(Math.abs(ctx.predictedZoom().start + ctx.predictedZoom().span * .3 - 103) < 1e-9);
    console.log('PASS recording limits and repeated wheel factors preserve zoom geometry');

    reset();
    for (let i = 0; i < 5; i++) ctx.cacheRenderedView({ ...cached(), viewSpan: 20 * (i + 1) });
    ctx.scheduleZoomPrefetch(); fireTimer(app.prefetchTimer);
    assert.equal(calls.length, 0, 'A full visited cache must prevent speculative work');
    const visited = app.renderCache.slice();
    ctx.cacheRenderedView({ ...cached(), speculative: true });
    assert.deepEqual(app.renderCache, visited, 'Speculation must not evict visited views');
    reset();
    const first = { ...cached(), speculative: true }, second = { ...cached(), speculative: true };
    ctx.cacheRenderedView(first); ctx.cacheRenderedView(second);
    assert(!app.renderCache.includes(first)); assert(app.renderCache.includes(second));
    assert.equal(app.renderCache.filter(r => r.speculative).length, 1);
    for (let i = 0; i < 5; i++) ctx.cacheRenderedView({ ...cached(), viewSpan: 20 * (i + 1) });
    assert(!app.renderCache.includes(second), 'Unused predictions must be evicted before visited levels');
    reset();
    ctx.cacheRenderedView({ ...cached(), image: { width: 2000, height: 1900 } });
    ctx.scheduleZoomPrefetch(); fireTimer(app.prefetchTimer); assert.equal(calls.length, 0);
    assert(app.renderCacheBytes <= 16 * 1048576 && app.renderCache.length <= 6);
    assert.equal(app.renderCacheBytes, app.renderCache.reduce((sum, r) => sum + r.cacheBytes, 0));
    console.log('PASS shared cache budget, at most one unused prediction and visited-view priority');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
