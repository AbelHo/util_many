// Run: node helper/audio_annotatorv2.html/zoom_test.cjs
// Exercises the actual inline worker and view scheduler without browser packages.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../../audio_annotatorv2.html'), 'utf8');
const worker = html.match(/<script id="audio-worker"[^>]*>([\s\S]*?)<\/script>/)[1];
function section(start, end) {
    const a = html.indexOf(start), b = html.indexOf(end, a);
    assert(a >= 0 && b > a);
    return html.slice(a, b);
}
const rate = 192000, duration = 2048.046;
const sampleAt = i => Math.fround(Math.sin(i * Math.PI / 16) * .25 + (i % 997 === 0 ? .5 : 0));
let reads = 0, frames = 0, sleeps = 0, releaseRead = null;
const source = { sampleRate: rate, frames: Math.floor(rate * duration), channels: 5,
    bytes: { cache: { bytes: 0 }, readBytes: 0 },
    async read(start, count) {
        reads++; frames += count;
        if (releaseRead) await new Promise(resolve => { releaseRead = resolve; });
        return Float32Array.from({ length: count }, (_, i) => sampleAt(start + i));
    } };
const messages = new Map(), waiters = new Map();
const ctx = vm.createContext({ console, self: {}, testSource: source,
    // A fast/cached operation must not incur dozens of mandatory timer waits.
    performance: { now: () => 0 },
    setTimeout: fn => { sleeps++; return setTimeout(fn, 0); },
    postMessage: m => { messages.set(m.id, m); waiters.get(m.id)?.(m); } });
vm.runInContext(worker + '\nsource = testSource; renderToken = 1;', ctx);
const api = vm.runInContext('({render,envelope,spectrum,palette})', ctx);
function params(start, span, preview = false) {
    const height = preview ? 128 : 200;
    return { start, span, preview, width: 1000, height, channel: 0, fft: 2048,
        fmin: 0, fmax: rate / 2, scale: 'linear', color: 'ember', dbMin: -100, dbMax: 0,
        frequencyEdges: Array.from({ length: height + 1 }, (_, y) => (1 - y / height) * rate / 2) };
}
async function main() {
    const quick = await api.render(params(0, duration, true), 1);
    assert.equal(quick.preview, true);
    assert(quick.width <= 256 && quick.columns <= 64);
    assert(frames <= 65536 + 64 * 2048, 'Quick view must have a fixed sample budget independent of file length');
    assert.equal(sleeps, 0, 'Cached work must not pay fixed per-column timer delays');
    console.log('PASS bounded whole-recording quick preview; no mandatory column sleeps');

    const p = params(1000, .001), r = await api.render(p, 1);
    assert.equal(r.mode, 'samples');
    for (let i = 0; i < r.samples.length; i++) assert.equal(r.samples[i], sampleAt(r.firstSample + i));
    // Independent per-pixel reference checks that cached colored columns retain
    // the original hop-aligned FFT/time geometry and peak-bin mapping.
    const colors = api.palette(p.color), dbByCenter = new Map();
    for (let x = 0; x < r.columns; x++) {
        const center = Math.round((p.start + (x + .5) / r.columns * p.span) * rate / 512) * 512;
        if (!dbByCenter.has(center)) dbByCenter.set(center, api.spectrum(await source.read(center - 1024, 2048), 2048));
        const db = dbByCenter.get(center);
        for (let y = 0; y < r.height; y++) {
            const a = Math.max(0, Math.floor(p.frequencyEdges[y + 1] * 2048 / rate));
            const b = Math.min(1024, Math.ceil(p.frequencyEdges[y] * 2048 / rate));
            let value = -180;
            for (let k = a; k <= b; k++) value = Math.max(value, db[k]);
            const color = colors[Math.max(0, Math.min(255, Math.round((value + 100) / 100 * 255)))];
            const i = (y * r.columns + x) * 4;
            assert.deepEqual(Array.from(r.pixels.slice(i, i + 4)), [...color, 255]);
        }
    }
    assert(dbByCenter.size <= 2);
    const exact = await api.envelope(2, 2.1, 100, 0, 1);
    const reference = Array.from({ length: 100 }, () => [Infinity, -Infinity]);
    const first = Math.floor(2 * rate), last = Math.ceil(2.1 * rate);
    for (let i = first; i < last; i++) {
        const bin = Math.min(99, Math.floor((i - first) / (last - first) * 100)), value = sampleAt(i);
        reference[bin][0] = Math.min(reference[bin][0], value);
        reference[bin][1] = Math.max(reference[bin][1], value);
    }
    assert.deepEqual(Array.from(exact.wave), reference.flat());
    console.log('PASS native samples, exact envelope and all spectrogram pixels match their reference');

    // Hold the first I/O operation, then supersede both the active and queued jobs.
    releaseRead = true;
    await ctx.self.onmessage({ data: { type: 'render', id: 1, params: params(0, duration, true) } });
    const unblock = releaseRead; releaseRead = null;
    await ctx.self.onmessage({ data: { type: 'render', id: 2, params: params(100, 10, true) } });
    await ctx.self.onmessage({ data: { type: 'render', id: 3, params: params(1000, .001) } });
    const completed = new Promise(resolve => waiters.set(3, resolve));
    unblock();
    const latest = await completed;
    assert(messages.get(1).result.cancelled && messages.get(2).result.cancelled);
    assert.equal(latest.result.start, 1000);
    assert.equal(latest.result.preview, false);
    console.log('PASS rapid replacement cancels active/queued work and completes the latest view');

    let next = 1, paints = 0, cancels = 0;
    const timers = new Map(), animationFrames = new Map(), renders = [];
    const elements = new Map();
    const app = { meta: {}, renderSerial: 0, renderTimer: 0, refineTimer: 0, renderFrame: 0,
        analysis: { call: () => { cancels++; return Promise.resolve(); } } };
    const ui = vm.createContext({ app, $: id => {
        if (!elements.has(id)) elements.set(id, { value: 'ember', style: {}, setAttribute() {} });
        return elements.get(id);
    }, setTimeout: fn => { const id = next++; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id),
    requestAnimationFrame: fn => { const id = next++; animationFrames.set(id, fn); return id; },
    paintAll: () => paints++, doRender: (...args) => renders.push(args) });
    vm.runInContext(section('    function requestRender()', '    async function doRender(') +
        section('    function clippedImageRect(', '    function drawBase('), ui);
    for (let i = 0; i < 100; i++) ui.requestRender();
    assert.equal(timers.size, 1); assert.equal(animationFrames.size, 1); assert.equal(cancels, 1);
    const [frameId, frame] = [...animationFrames][0]; animationFrames.delete(frameId); frame();
    assert.equal(paints, 1);
    // More input must not push back the original render deadline.
    const deadline = app.renderTimer;
    for (let i = 0; i < 100; i++) ui.requestRender();
    assert.equal(app.renderTimer, deadline);
    const timer = timers.get(deadline); timers.delete(deadline); timer();
    assert.deepEqual(renders, [[200, true]]);
    // Background tabs can deliver a frame after worker completion. It must not
    // replace completed/refining status with an obsolete "Updating" message.
    elements.get('renderInfo').textContent = 'Completed';
    for (const callback of animationFrames.values()) callback();
    assert.equal(elements.get('renderInfo').textContent, 'Completed');
    const g = { left: 64, top: 23, w: 1000, h: 200 };
    const rect = ui.clippedImageRect(-1e12, -1e9, 2e12, 2e9, g, 640, 200);
    assert.deepEqual(Array.from(rect.slice(4)), [64, 23, 1000, 200]);
    assert.equal(ui.clippedImageRect(2000, 0, 100, 200, g, 640, 200), null);
    console.log('PASS 200 zoom inputs coalesce; deadline is retained; stale image scaling stays inside viewport');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
