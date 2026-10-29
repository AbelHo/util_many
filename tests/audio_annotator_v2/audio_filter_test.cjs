// Run: node tests/audio_annotator_v2/audio_filter_test.cjs
// Tests the actual embedded DSP worker with no browser, npm packages or fixtures.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.resolve(__dirname, '../../audio_annotatorv2.html'), 'utf8');
const workerCode = html.match(/<script id="audio-worker" type="text\/plain">([\s\S]*?)<\/script>/)?.[1];
const mainCode = html.match(/<script>\s*([\s\S]*?)<\/script>/)?.[1];
assert.ok(workerCode && mainCode, 'Expected both embedded scripts');
new Function('document', 'window', mainCode); // Parse main UI script without executing the DOM code.
for (const id of ['highPassHz', 'lowPassHz', 'audioFilterInfo']) {
    assert.match(html, new RegExp('id="' + id + '"'), 'Missing control ' + id);
}
function workerFor(source) {
    // Workers own their settings and caches, as in a new browser file load.
    const api = new Function('postMessage', 'self', 'performance', 'setTimeout', workerCode +
        '\nreturn { setSource: value => source = value, updateAudioFilter, filteredRead, audioChunk, filterSettingsKey, createOverview, statistics };')(
            () => {}, {}, { now: () => Date.now() }, setTimeout);
    api.setSource(source);
    return api;
}
const sampleRate = 96000, frames = sampleRate * 2;
const tone = (hz, frame) => Math.sin(2 * Math.PI * hz * frame / sampleRate);
const sample = (frame, channel) => {
    const a = .16 * tone(1000, frame) + .17 * tone(8000, frame) + .14 * tone(18000, frame);
    const b = .12 * tone(3000, frame) + .11 * tone(12000, frame);
    return channel === -1 ? (a + b) / 2 : channel === 1 ? b : a;
};
function sourceFor(fn = sample) {
    return {
        sampleRate, frames, channels: 2, format: 'synthetic',
        bytes: { cache: { bytes: 0 }, readBytes: 0 },
        async read(start, count, channel) {
            assert.ok(Number.isInteger(start) && Number.isInteger(count) && count <= 4194304);
            const out = new Float32Array(count);
            for (let i = 0; i < count; i++)
                if (start + i >= 0 && start + i < frames) out[i] = fn(start + i, channel);
            return out;
        }
    };
}
function amplitude(data, start, hz) {
    let re = 0, im = 0;
    for (let i = 0; i < data.length; i++) {
        const a = 2 * Math.PI * hz * (start + i) / sampleRate;
        re += data[i] * Math.cos(a);
        im += data[i] * Math.sin(a);
    }
    return 2 * Math.hypot(re, im) / data.length;
}
const near = (a, b, eps = 2e-6) => assert.ok(Math.abs(a - b) < eps, a + ' not close to ' + b);
(async () => {
    const source = sourceFor(), worker = workerFor(source);
    const start = 16700, length = 32768;
    assert.equal(worker.filterSettingsKey(), 'off');
    assert.deepEqual(await worker.filteredRead(start, 512, 0), await source.read(start, 512, 0));

    const cases = [
        { name: 'low-pass', f: { high: null, low: 4000 }, pass: [1000], reject: [8000, 18000] },
        { name: 'high-pass', f: { high: 10000, low: null }, pass: [18000], reject: [1000, 8000] },
        { name: 'band-pass', f: { high: 5000, low: 12000 }, pass: [8000], reject: [1000, 18000] }
    ];
    for (const c of cases) {
        const settings = worker.updateAudioFilter(c.f);
        assert.ok(settings.taps >= 65 && settings.taps <= 4097 && settings.taps % 2 === 1);
        assert.equal(worker.filterSettingsKey(), JSON.stringify([c.f.high, c.f.low]));
        const filtered = await worker.filteredRead(start, length, 0);
        const middle = filtered.subarray(4096, length - 4096);
        for (const hz of c.pass) {
            const actual = amplitude(middle, start + 4096, hz);
            assert.ok(actual > .1, c.name + ' attenuated wanted frequency ' + hz + ' Hz: ' + actual);
        }
        for (const hz of c.reject) {
            const actual = amplitude(middle, start + 4096, hz);
            assert.ok(actual < .015, c.name + ' leaked unwanted frequency ' + hz + ' Hz: ' + actual);
        }
        const boundaryStart = 32762;
        const randomRead = await worker.filteredRead(boundaryStart, 100, 0);
        const largeRead = await worker.filteredRead(start, length, 0);
        for (let i = 0; i < randomRead.length; i++)
            near(randomRead[i], largeRead[boundaryStart - start + i]);
        const next = await worker.filteredRead(32000, 1024, -1);
        const ch0 = await worker.filteredRead(32000, 1024, 0);
        const ch1 = await worker.filteredRead(32000, 1024, 1);
        for (let i = 0; i < next.length; i++) near(next[i], (ch0[i] + ch1[i]) / 2);
        const audio = await worker.audioChunk({ position: 32000, frames: 512, speed: 1,
            outputRate: sampleRate, channel: 0 });
        for (let i = 0; i < audio.data.length; i++) near(audio.data[i], ch0[i]);
        assert.ok(worker.statistics().filterCache > 0, 'Filtered caches should be used');
        const overview = worker.createOverview(0, 1024);
        assert.equal(overview.filterKey, worker.filterSettingsKey());
        console.log('PASS ' + c.name + ' spectral selectivity, random reads, channel mix, playback, overview keys');
    }
    for (const config of [{ high: 5000, low: 5000 }, { high: 17000, low: 8000 },
        { high: 48000, low: null }, { high: -1, low: null }, { high: NaN, low: null }]) {
        const before = worker.filterSettingsKey();
        assert.throws(() => worker.updateAudioFilter(config));
        assert.equal(worker.filterSettingsKey(), before, 'Invalid edits must leave prior filter intact');
    }
    worker.updateAudioFilter(null);
    assert.equal(worker.filterSettingsKey(), 'off');
    assert.deepEqual(await worker.filteredRead(start, 512, 0), await source.read(start, 512, 0));

    const impulse = workerFor(sourceFor((frame) => frame === 20000 ? 1 : 0));
    impulse.updateAudioFilter({ high: null, low: 4000 });
    const response = await impulse.filteredRead(19900, 201, 0);
    for (let k = 1; k <= 98; k++) near(response[100 - k], response[100 + k], 1e-5);
    assert.ok(response[100] > .04, 'Impulse should stay at the native-sample timestamp');
    console.log('PASS disabled bypass, invalid-cutoff rollback, zero-phase impulse alignment');
})().catch(e => { console.error(e); process.exitCode = 1; });
