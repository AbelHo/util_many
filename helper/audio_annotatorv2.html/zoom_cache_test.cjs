// Run: node helper/audio_annotatorv2.html/zoom_cache_test.cjs
const assert = require('node:assert/strict');
const { app, ctx, $, timers, calls, cached, fireTimer, flushFrames, finish } = require('./pan_cache_test.cjs');
async function main() {
    const original = cached(); ctx.cacheRenderedView(original);
    app.start = 102.5; app.span = 5;
    ctx.requestRender(); flushFrames();
    assert(app.lastRender === original, 'A covering cached zoom must appear immediately');
    assert.equal(app.renderPending, true, 'Upscaling a coarse view must still require new detail');
    assert.match($('renderInfo').textContent, /^Cached zoom preview/);
    fireTimer();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].p.preview, false, 'Existing cached preview should skip redundant quick analysis');
    await finish(calls[0]);
    assert.equal(app.lastRender.viewSpan, 5);
    assert.equal(app.renderPending, false);
    const detailed = app.lastRender;
    app.start = 100; app.span = 10; ctx.requestRender(); flushFrames();
    assert(app.lastRender === original);
    assert.equal(app.renderPending, false);
    assert.equal(app.renderTimer, 0);
    app.start = 102.5; app.span = 5; ctx.requestRender(); flushFrames();
    assert(app.lastRender === detailed);
    assert.equal(calls.length, 1, 'Returning to either level must not run analysis again');
    console.log('PASS immediate cross-level preview, mandatory refinement and instant zoom round trips');

    app.start = 100; app.span = 10 * (1 + 1e-12);
    assert(ctx.cachedView() === original, 'Wheel round-off should not defeat an otherwise identical zoom level');
    app.span = 10.01;
    assert.equal(ctx.cachedView(), null, 'A materially different zoom must not be treated as final detail');
    app.start = 100; app.span = .01;
    assert.equal(ctx.cachedZoomPreview(), null, 'Extremely magnified old previews must not be substituted');
    app.start = 500; app.span = 5;
    assert.equal(ctx.cachedZoomPreview(), null, 'Wrong time range must not be reused');
    app.start = 102.5; $('fftSize').value = '4096';
    assert.equal(ctx.cachedZoomPreview(), null, 'Wrong FFT settings must not be reused');
    $('fftSize').value = '2048';
    console.log('PASS floating-point zoom tolerance, coverage, resolution bounds and settings isolation');

    app.renderCache = []; app.renderCacheBytes = 0;
    const wide = { ...cached(), viewSpan: 40 }, medium = { ...cached(), viewSpan: 20 };
    ctx.cacheRenderedView(wide); ctx.cacheRenderedView(medium);
    for (let i = 0; i < 10; i++) ctx.cacheRenderedView(cached(i * 2));
    assert.equal(app.renderCache.length, 6);
    assert(app.renderCache.includes(wide) && app.renderCache.includes(medium),
        'Repeated panning at one zoom must preserve the other recent levels');
    const touched = app.renderCache[2]; ctx.touchRenderedView(touched);
    ctx.cacheRenderedView(cached(50));
    assert(app.renderCache.includes(touched), 'Recently reused data must survive before older duplicate views');
    assert.equal(app.renderCacheBytes, app.renderCache.reduce((sum, r) => sum + r.cacheBytes, 0));
    assert(app.renderCacheBytes <= 16 * 1048576);
    console.log('PASS bounded cache retains recent zoom levels and recently reused views');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
