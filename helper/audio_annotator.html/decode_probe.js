// decode_probe.js — diagnostic that demonstrates *why* native-rate decoding is
// needed. It decodes the 96 kHz sample two ways inside the browser:
//   1. a default AudioContext  -> resamples to the hardware rate (~44.1 kHz),
//      so everything above ~22 kHz is lost;
//   2. an AudioContext opened at { sampleRate: 96000 } -> keeps the native rate.
// This is the behaviour the app relies on (see ensureAudioContext()).
//
// Requires Playwright. Run from anywhere:
//   node helper/audio_annotator.html/decode_probe.js
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '../..');
const HTML = 'file://' + path.join(ROOT, 'audio_annotator.html');
const WAV = path.join(ROOT, 'sample', '251006_001_0002.WAV');

(async () => {
  // fetch() is blocked on file://, so inject the bytes as base64.
  const b64 = fs.readFileSync(WAV).toString('base64');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(HTML);
  const r = await page.evaluate(async (b64) => {
    const bin = atob(b64); const u8 = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    const ab = u8.buffer;

    const def = new AudioContext();
    const defRate = def.sampleRate;
    const defBuf = await def.decodeAudioData(ab.slice(0));

    let nativeRate = null, nativeBuf = null, err = null;
    try {
      const hc = new AudioContext({ sampleRate: 96000 });
      const hb = await hc.decodeAudioData(ab.slice(0));
      nativeRate = hc.sampleRate; nativeBuf = hb.sampleRate;
    } catch (e) { err = e.message; }

    return { defaultCtxRate: defRate, decodedWithDefault: defBuf.sampleRate,
             nativeCtxRate: nativeRate, decodedWithNative: nativeBuf, nativeError: err };
  }, b64);

  console.log(JSON.stringify(r, null, 2));
  const ok = r.decodedWithDefault < 96000 && r.decodedWithNative === 96000;
  console.log(ok
    ? '\nPASS  default context resamples; explicit 96 kHz context preserves the native rate'
    : '\nNOTE  unexpected decode behaviour on this browser/platform');
  await browser.close();
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
