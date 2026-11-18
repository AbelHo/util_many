// Run: node tests/audio_annotator_v2/large_wav_test.cjs
// Exercise the actual embedded WAV reader using virtual sparse files: no large
// allocation, browser, npm package, or external audio fixture is required.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.resolve(__dirname, '../../audio_annotatorv2.html'), 'utf8');
const workerCode = html.match(/<script id="audio-worker" type="text\/plain">([\s\S]*?)<\/script>/)?.[1];
assert.ok(workerCode, 'Expected the embedded audio worker');
const { Bytes, WavSource } = new Function('postMessage', 'self', 'performance', 'setTimeout',
    workerCode + '\nreturn { Bytes, WavSource };')(() => {}, {}, { now: Date.now }, setTimeout);

const MAX = 0xffffffff, frames = 300000000, align = 15, dataBytes = frames * align;
function chunk(id, data) {
    const h = Buffer.alloc(8);
    h.write(id, 0, 'ascii'); h.writeUInt32LE(data.length, 4);
    return Buffer.concat([h, data, data.length % 2 ? Buffer.alloc(1) : Buffer.alloc(0)]);
}
function fmt() {
    // WAVE_FORMAT_EXTENSIBLE, five-channel 24-bit PCM, as in the recordings.
    const b = Buffer.alloc(40);
    b.writeUInt16LE(0xfffe, 0); b.writeUInt16LE(5, 2); b.writeUInt32LE(192000, 4);
    b.writeUInt32LE(192000 * align, 8); b.writeUInt16LE(align, 12); b.writeUInt16LE(24, 14);
    b.writeUInt16LE(22, 16); b.writeUInt16LE(24, 18); b.writeUInt32LE(0x37, 20);
    Buffer.from('0100000000001000800000aa00389b71', 'hex').copy(b, 24);
    return chunk('fmt ', b);
}
function header({ kind = 'RIFF', riffSize = MAX, declaredData = MAX, ds64 = false, beforeFmt = false, dataId = 'data' } = {}) {
    const h = Buffer.alloc(12);
    h.write(kind); h.writeUInt32LE(riffSize, 4); h.write('WAVE', 8);
    const dh = Buffer.alloc(8); dh.write(dataId); dh.writeUInt32LE(declaredData, 4);
    const parts = [h];
    if (ds64) {
        const ds = Buffer.alloc(28);
        ds.writeBigUInt64LE(BigInt(dataBytes + 100), 0);
        ds.writeBigUInt64LE(BigInt(dataBytes), 8);
        ds.writeBigUInt64LE(BigInt(frames), 16);
        parts.push(chunk('ds64', ds));
    }
    if (!beforeFmt) parts.push(fmt(), chunk('LIST', Buffer.from('INFO')));
    parts.push(dh);
    return Buffer.concat(parts);
}
function sparseFile(head, dataLength, patches = []) {
    const size = head.length + dataLength;
    const sections = [{ offset: 0, bytes: head }, ...patches];
    let largestSlice = 0, totalRead = 0;
    return {
        size,
        get largestSlice() { return largestSlice; },
        get totalRead() { return totalRead; },
        slice(start, end) {
            assert.ok(start >= 0 && end <= size && end >= start);
            largestSlice = Math.max(largestSlice, end - start);
            totalRead += end - start;
            const out = new Uint8Array(end - start);
            for (const section of sections) {
                const from = Math.max(start, section.offset), to = Math.min(end, section.offset + section.bytes.length);
                if (from < to) out.set(section.bytes.subarray(from - section.offset, to - section.offset), from - start);
            }
            return { arrayBuffer: async () => out.buffer };
        }
    };
}
async function open(file) { return new WavSource(file, new Bytes(file)).init(); }

async function main() {
    const h = header();
    const first = Buffer.alloc(align), last = Buffer.alloc(align);
    first.writeIntLE(4194304, 6, 3); last.writeIntLE(-2097152, 6, 3);
    const file = sparseFile(h, dataBytes, [
        { offset: h.length, bytes: first },
        { offset: h.length + dataBytes - align, bytes: last }
    ]);
    const wav = await open(file);
    assert.equal(wav.frames, frames);
    assert.equal(wav.sampleRate, 192000); assert.equal(wav.channels, 5); assert.equal(wav.bits, 24);
    assert.equal(wav.segments[0].offset, h.length); assert.equal(wav.segments[0].bytes, dataBytes);
    assert.match(wav.format, /data extends to EOF; trailing chunks cannot be detected/);
    assert.deepEqual(Array.from(await wav.read(0, 1, 2)), [0.5]);
    assert.deepEqual(Array.from(await wav.read(frames - 1, 1, 2)), [-0.25]);
    assert.ok(file.largestSlice <= 65536 && file.totalRead < 1024 * 1024, 'Reads must remain bounded');
    console.log('PASS oversized saturated RIFF: metadata, warning, first/last samples and bounded reads');

    const rfHeader = header({ kind: 'RF64', ds64: true });
    const rf = await open(sparseFile(rfHeader, dataBytes));
    assert.equal(rf.frames, frames);
    assert.equal(rf.format, 'RF64 PCM 24-bit');
    const tail = chunk('JUNK', Buffer.alloc(0));
    const riffWithDs = header({ ds64: true });
    const declared = await open(sparseFile(riffWithDs, dataBytes + tail.length,
        [{ offset: riffWithDs.length + dataBytes, bytes: tail }]));
    assert.equal(declared.frames, frames, 'Explicit ds64 length must win over EOF inference');
    assert.equal(declared.format, 'RIFF PCM 24-bit');
    const normalHeader = header({ riffSize: 100, declaredData: 2 * align });
    const normal = await open(sparseFile(normalHeader, 2 * align));
    assert.equal(normal.frames, 2); assert.equal(normal.format, 'RIFF PCM 24-bit');
    console.log('PASS RF64 ds64 and normal RIFF keep their declared sizes');

    const missing = /missing its ds64 size/;
    await assert.rejects(() => open(sparseFile(header({ kind: 'RF64' }), dataBytes)), missing);
    await assert.rejects(() => open(sparseFile(header({ kind: 'BW64' }), dataBytes)), missing);
    await assert.rejects(() => open(sparseFile(header({ riffSize: 123 }), dataBytes)), missing);
    await assert.rejects(() => open(sparseFile(header(), 2 * align)), missing);
    await assert.rejects(() => open(sparseFile(header({ beforeFmt: true }), dataBytes)), missing);
    await assert.rejects(() => open(sparseFile(header({ dataId: 'JUNK' }), dataBytes)), missing);
    await assert.rejects(() => open(sparseFile(header(), dataBytes - 1)), /partial sample frame/);
    const truncated = header({ kind: 'RF64', ds64: true });
    await assert.rejects(() => open(sparseFile(truncated, dataBytes - 1)), /Truncated WAV data chunk/);
    console.log('PASS malformed or ambiguous headers and incomplete frames are rejected');

    // Run v2's real message handler with a minimal window, without loading a UI.
    const handler = html.match(/window\.addEventListener\('message', event => \{[\s\S]*?\n    \}\);/)?.[0];
    assert.ok(handler, 'Expected the embedded-view message handler');
    const parent = {}, other = {}, seen = [], errors = [];
    let listener;
    const win = { parent, addEventListener: (type, fn) => { assert.equal(type, 'message'); listener = fn; } };
    new Function('window', 'File', 'loadAudio', 'report', handler)(win, File,
        file => { seen.push(file); return Promise.resolve(); }, error => errors.push(error));
    const input = new File(['samples'], 'sound.wav');
    listener({ source: other, data: { type: 'audio-annotator-open-large-wav', file: input } });
    listener({ source: parent, data: { type: 'other', file: input } });
    listener({ source: parent, data: { type: 'audio-annotator-open-large-wav', file: {} } });
    listener({ source: parent, data: null });
    assert.equal(seen.length, 0);
    listener({ source: parent, data: { type: 'audio-annotator-open-large-wav', file: input } });
    assert.deepEqual(seen, [input]); assert.deepEqual(errors, []);
    win.parent = win;
    listener({ source: win, data: { type: 'audio-annotator-open-large-wav', file: input } });
    assert.equal(seen.length, 1, 'A top-level page must ignore forwarded files');
    console.log('PASS embedded-view handler accepts only a parent message containing a File');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
