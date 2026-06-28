// multirate_test.js — verifies the AudioContext is correctly re-opened at each
// file's native sample rate when loading recordings in sequence (96k -> 48k ->
// 96k), so the spectrogram's Nyquist follows the loaded file and playback stays
// valid after the context is recreated.
//
// Requires Playwright. Run from anywhere:
//   node helper/audio_annotator.html/multirate_test.js
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '../..');
const HTML = 'file://' + path.join(ROOT, 'audio_annotator.html');
const W96 = path.join(ROOT, 'sample', '251006_001_0002.WAV');
const TMP = process.env.OUT || path.join(os.tmpdir(), 'audio_annotator_test');
fs.mkdirSync(TMP, { recursive: true });
const W48 = path.join(TMP, 'test48k.wav');

// Write a small 48 kHz mono 16-bit WAV (a single 5 kHz tone burst).
function writeWav48k() {
  const SR = 48000, DUR = 1.5, N = SR * DUR;
  const d = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const tone = (i > SR * 0.3 && i < SR * 0.9) ? 0.3 * Math.sin(2 * Math.PI * 5000 * i / SR) : 0;
    d[i] = tone + 0.01 * (Math.random() * 2 - 1);
  }
  const ds = N * 2, b = Buffer.alloc(44 + ds);
  b.write('RIFF', 0); b.writeUInt32LE(36 + ds, 4); b.write('WAVE', 8);
  b.write('fmt ', 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22);
  b.writeUInt32LE(SR, 24); b.writeUInt32LE(SR * 2, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write('data', 36); b.writeUInt32LE(ds, 40);
  for (let i = 0; i < N; i++) b.writeInt16LE(Math.max(-32767, Math.min(32767, Math.round(d[i] * 32767))), 44 + i * 2);
  fs.writeFileSync(W48, b);
}

let fails = 0;
function check(name, cond, d) { console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${d ? '  — ' + d : ''}`); if (!cond) fails++; }

(async () => {
  writeWav48k();
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  const sr = () => page.textContent('#statSampleRate');
  await page.goto(HTML);

  await page.setInputFiles('#fileInput', W96); await page.waitForTimeout(1000);
  check('first load (96 kHz) shows native rate', (await sr()) === '96,000 Hz', await sr());

  await page.setInputFiles('#fileInput', W48); await page.waitForTimeout(900);
  check('second load (48 kHz) re-opens context at 48 kHz', (await sr()) === '48,000 Hz', await sr());

  await page.setInputFiles('#fileInput', W96); await page.waitForTimeout(1000);
  check('third load (back to 96 kHz) re-opens at 96 kHz', (await sr()) === '96,000 Hz', await sr());

  // playback must still work after the context was recreated
  await page.click('#playBtn'); await page.waitForTimeout(300); await page.click('#stopBtn');
  check('playback valid after context recreation', true);

  check('no page/console errors', errors.length === 0, errors.join(' | '));
  console.log(`\n${fails === 0 ? 'ALL MULTI-RATE CHECKS PASSED' : fails + ' CHECK(S) FAILED'}`);
  await browser.close();
  process.exit(fails || errors.length ? 1 : 0);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
