// Run: node helper/audio_annotatorv2.html/overview_test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../../audio_annotatorv2.html'), 'utf8');
const worker = html.match(/<script id="audio-worker"[^>]*>([\s\S]*?)<\/script>/)[1];
const rate = 192000, frames = 4194304 + 17, fft = 2048;
const impulses = new Map([[1, .9], [65535, -.8], [65536, .7], [131073, -.6], [frames - 1, .75]]);
function sampleAt(i) {
    if (i < 0 || i >= frames) return 0;
    return Math.fround(impulses.get(i) ?? (i >= 1234000 && i < 1235500 ? .2 * Math.sin(i * Math.PI / 8) : 0));
}
let reads = 0, readSamples = 0, maxRead = 0, blockRead = null;
const source = { frames, sampleRate: rate, channels: 2,
    bytes: { cache: { bytes: 0 }, readBytes: 0 },
    async read(start, count, channel) {
        reads++; readSamples += count; maxRead = Math.max(maxRead, count);
        if (blockRead) await new Promise(resolve => { blockRead = resolve; });
        return Float32Array.from({length:count}, (_, i) => channel === 1 ? 0 : sampleAt(start + i));
    } };
const events = [];
const ctx = vm.createContext({ console, performance, setTimeout, self: {}, testSource: source, postMessage: m => events.push(m) });
vm.runInContext(worker + '\nsource = testSource; renderToken = 1;', ctx);
const api = vm.runInContext('({createOverview, overviewLoop, overviewLevel, overviewBytes, render, envelope, spectrum, finishOverview})', ctx);
const current = () => vm.runInContext('overview', ctx);
function params(start = 0, span = frames / rate, channel = 0) {
    return {start, span, channel, fft, width:64, height:64, fmin:0, fmax:rate/2, scale:'linear', color:'gray', dbMin:-110, dbMax:0,
        frequencyEdges:Array.from({length:65}, (_,i)=>(64-i)/64*rate/2)};
}
async function main() {
    const old = await api.render(params(), 1);
    assert.equal(old.mode, 'sampled'); assert.equal(old.spectrumMode, 'sampled');
    reads = readSamples = maxRead = 0;
    vm.runInContext('overview = createOverview(0, 2048); overview.active = true; overviewToken = 1;', ctx);
    await api.overviewLoop(1);
    const o = current();
    assert.equal(o.complete, true); assert.equal(o.nextFrame, Math.ceil(frames / 512));
    assert(readSamples <= frames + Math.ceil(frames / 65536) * fft, 'Both summaries must share one sequential scan with only FFT overlap');
    assert(maxRead <= 65536 + fft); assert(o.waveLevels.length > 1 && o.specLevels.length > 1);
    assert(api.overviewBytes(o) < 20 * 1048576);
    const base = o.waveLevels[0];
    const lo = new Float32Array(base.min.length).fill(Infinity), hi = new Float32Array(base.max.length).fill(-Infinity);
    for (let i = 0; i < frames; i++) { const b = Math.floor(i / base.block), v = sampleAt(i); lo[b] = Math.min(lo[b],v); hi[b] = Math.max(hi[b],v); }
    assert.deepEqual(Array.from(base.min),Array.from(lo)); assert.deepEqual(Array.from(base.max),Array.from(hi));
    const top = o.waveLevels.at(-1);
    assert.equal(top.max[0], Math.fround(.9)); assert.equal(top.min[0], Math.fround(-.8));
    console.log('PASS single bounded scan; every waveform sample, chunk boundary and EOF impulse preserved at all levels');

    const expected = new Int16Array(o.specLevels[0].peaks.length).fill(-32768), scratch = new Float32Array(fft/2+1);
    for (let frame = 0; frame < o.frameCount; frame++) {
        const a = Float32Array.from({length:fft}, (_,i)=>sampleAt(frame * o.hop - fft/2+i));
        api.spectrum(a, fft, scratch);
        const offset = Math.floor(frame/o.group)*o.bands;
        for (let k=0;k<scratch.length;k++) { const b=offset+Math.floor(k/o.freqGroup); expected[b]=Math.max(expected[b],Math.round(scratch[k]*4)); }
    }
    assert.deepEqual(Array.from(o.specLevels[0].peaks), Array.from(expected));
    for (let level = 1; level < o.specLevels.length; level++) {
        const prev=o.specLevels[level-1], next=o.specLevels[level];
        for(let t=0;t<next.count;t++) for(let b=0;b<o.bands;b++)
            assert.equal(next.peaks[t*o.bands+b],Math.max(prev.peaks[t*2*o.bands+b],prev.peaks[(t*2+1)*o.bands+b]??-32768));
    }
    const beforeReads = reads, indexed = await api.render(params(),1);
    assert.equal(indexed.mode, 'indexed'); assert.equal(indexed.spectrumMode, 'pooled');
    assert.equal(reads,beforeReads,'Indexed wide rendering must not reread audio');
    assert(indexed.wave[1] > .89 && old.wave[1] === 0, 'Overview must expose the impulse skipped by the old waveform preview');
    assert(indexed.pixels[0] > old.pixels[0], 'Overview must expose FFT energy skipped by the old spectrogram columns');
    const narrow=await api.render(params(1,.002),1); assert.equal(narrow.spectrumMode,'sampled');
    const wrong=await api.render({...params(),fft:4096},1); assert.equal(wrong.spectrumMode,'sampled');
    const other=await api.render(params(0,frames/rate,1),1); assert.equal(other.mode,'sampled'); assert.equal(other.spectrumMode,'sampled');
    console.log('PASS every Hann FFT hop matches independent pooling; wide render performs zero reads; narrow/other FFT/channel use fresh detail');

    const reused=api.createOverview(0,4096,o); assert.equal(reused.waveLevels,o.waveLevels); assert.equal(reused.waveReady,true);
    const different=api.createOverview(1,4096,o); assert.notEqual(different.waveLevels,o.waveLevels);
    // Pause during an outstanding read; resuming must complete once without skipping samples.
    vm.runInContext('overview = createOverview(0, 2048); overview.active = true; overviewToken = 2;',ctx);
    blockRead=true; const paused=api.overviewLoop(2);
    while(typeof blockRead !== 'function') await new Promise(r=>setTimeout(r,1));
    vm.runInContext('overview.active = false; overviewToken++;',ctx); const release=blockRead; blockRead=null; release(); await paused;
    assert.equal(current().complete,false); assert.equal(current().nextFrame,0);
    const stale=current(); vm.runInContext('overview = createOverview(1, 2048); overview.active = true; overviewToken++;',ctx);
    await api.overviewLoop(3); assert.equal(current().nextFrame,0,'A stale token must never fill a new channel');
    ctx.resumeOverview=stale; vm.runInContext('overview=resumeOverview; overview.active=true; overviewToken=5;',ctx);
    await api.overviewLoop(5); assert.equal(current().complete,true);
    assert.deepEqual(Array.from(current().specLevels[0].peaks),Array.from(expected));
    assert.equal(events.filter(e=>e.event==='overviewError').length,0);
    console.log('PASS pause/resume, stale-job rejection, channel isolation and waveform reuse for new FFT settings');
}
main().catch(e=>{ console.error(e); process.exitCode=1; });
