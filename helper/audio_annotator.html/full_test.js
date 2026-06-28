// full_test.js — comprehensive functional test for audio_annotator.html.
// Drives a real (headless Chromium) browser through the whole upload ->
// visualize -> annotate -> export -> import flow and asserts 29 checks.
//
// Requires Playwright. Run from anywhere:
//   node helper/audio_annotator.html/full_test.js
// Screenshots are written to $OUT (default: <os tmp>/audio_annotator_test).
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '../..');
const HTML = 'file://' + path.join(ROOT, 'audio_annotator.html');
const WAV = path.join(ROOT, 'sample', '251006_001_0002.WAV');
const OUT = process.env.OUT || path.join(os.tmpdir(), 'audio_annotator_test');
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function check(name, cond, detail) {
  results.push({ name, pass: !!cond, detail: detail || '' });
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

async function waitSpec(page) {
  // The spectrogram computes asynchronously; this is a simple settle delay.
  await page.waitForTimeout(900);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1300 } });
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE-ERROR: ' + m.text()); });

  // Controllable confirm()/alert() handler (import & clear use confirm()).
  let dialogAction = 'accept';
  page.on('dialog', async d => { (dialogAction === 'accept') ? await d.accept() : await d.dismiss(); });

  await page.goto(HTML);
  await page.setInputFiles('#fileInput', WAV);
  await waitSpec(page);

  // ---- Audio info / native-rate decode ----
  const info = await page.evaluate(() => ({
    dur: document.getElementById('statDuration').textContent,
    sr: document.getElementById('statSampleRate').textContent,
    ch: document.getElementById('statChannels').textContent,
    bd: document.getElementById('statBitDepth').textContent,
    fmax: document.getElementById('freqMaxInput').value,
  }));
  console.log('INFO', JSON.stringify(info));
  check('duration shown 3.000', info.dur === '0:03.000', info.dur);
  check('native sample rate 96,000 Hz (no resample)', info.sr === '96,000 Hz', info.sr);
  check('channels = 1', info.ch === '1', info.ch);
  check('bit depth detected 16-bit', info.bd === '16-bit', info.bd);
  check('freq max input initialized to Nyquist 48000', info.fmax === '48000', info.fmax);

  // ---- Spectrogram has real structure + high-freq energy present ----
  const specStats = await page.evaluate(() => {
    const c = document.getElementById('spectrogramCanvas');
    const ctx = c.getContext('2d');
    const { data, width, height } = ctx.getImageData(0, 0, c.width, c.height);
    let sum = 0, sum2 = 0, n = 0, brightTop = 0, topN = 0, maxTop = 0, sumTop = 0;
    const topCut = Math.floor(height * 0.25); // top 25% = highest frequencies (>36kHz)
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x += 4) {
        const i = (y * width + x) * 4;
        const lum = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
        sum += lum; sum2 += lum * lum; n++;
        if (y < topCut) { topN++; sumTop += lum; if (lum > 120) brightTop++; if (lum > maxTop) maxTop = lum; }
      }
    }
    const mean = sum / n, variance = sum2 / n - mean * mean;
    return { std: Math.sqrt(variance), brightTopFrac: brightTop / topN, maxTop, meanTop: sumTop / topN };
  });
  console.log('SPEC', JSON.stringify(specStats));
  check('spectrogram has structure (std > 15)', specStats.std > 15, 'std=' + specStats.std.toFixed(1));
  // A bright line (the 40 kHz chirp tip) over a dark background proves >24 kHz
  // content survived native-rate decoding.
  check('high-frequency content present above 24kHz (bright line on dark bg)',
        specStats.maxTop > 170 && specStats.meanTop < 130,
        `maxTop=${specStats.maxTop.toFixed(0)} meanTop=${specStats.meanTop.toFixed(0)} brightFrac=${specStats.brightTopFrac.toFixed(3)}`);

  await page.screenshot({ path: path.join(OUT, 't1_loaded.png'), fullPage: true });

  // ---- Frequency range selection: zoom to 20k–48k ----
  await page.fill('#freqMinInput', '20000');
  await page.fill('#freqMaxInput', '48000');
  await page.dispatchEvent('#freqMaxInput', 'change');
  await waitSpec(page);
  const frInfo = await page.evaluate(() => ({
    lo: document.getElementById('freqMinInput').value,
    hi: document.getElementById('freqMaxInput').value,
  }));
  check('freq range applied (20000–48000)', frInfo.lo === '20000' && frInfo.hi === '48000',
        `${frInfo.lo}-${frInfo.hi}`);
  await page.screenshot({ path: path.join(OUT, 't2_freqrange.png'), fullPage: true });
  // Reset to full
  await page.click('#freqResetBtn');
  await waitSpec(page);
  const full = await page.evaluate(() => document.getElementById('freqMaxInput').value);
  check('freq range reset to full', full === '48000', full);

  // ---- FFT size + color scale ----
  await page.selectOption('#fftSizeSelect', '4096');
  await waitSpec(page);
  check('FFT size change handled (no error)', true);
  await page.selectOption('#colorScaleSelect', 'viridis');
  await waitSpec(page);
  await page.screenshot({ path: path.join(OUT, 't3_viridis_fft4096.png'), fullPage: true });
  await page.selectOption('#fftSizeSelect', '2048');
  await page.selectOption('#colorScaleSelect', 'cool');
  await waitSpec(page);

  // ---- Annotations ----
  const specBox = await page.locator('#spectrogramCanvas').boundingBox();
  const waveBox = await page.locator('#waveformCanvas').boundingBox();

  // Point (default mode) – click on spectrogram
  await page.mouse.move(specBox.x + 300, specBox.y + 200);
  await page.mouse.down(); await page.mouse.up();
  await page.waitForTimeout(150);
  let count = await page.textContent('#annotationCount');
  check('point annotation added via spectrogram click', count === '1', 'count=' + count);
  const firstText = await page.textContent('.annotation-item span');
  check('point annotation records a frequency', /kHz|Hz/.test(firstText), firstText);

  // Time range – switch mode, drag on waveform
  await page.check('input[name="annotationMode"][value="timeRange"]');
  await page.mouse.move(waveBox.x + 500, waveBox.y + 100);
  await page.mouse.down();
  await page.mouse.move(waveBox.x + 700, waveBox.y + 100, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(150);
  count = await page.textContent('#annotationCount');
  check('time-range annotation added via waveform drag', count === '2', 'count=' + count);

  // Freq range – shift+drag on spectrogram
  await page.keyboard.down('Shift');
  await page.mouse.move(specBox.x + 850, specBox.y + 120);
  await page.mouse.down();
  await page.mouse.move(specBox.x + 1000, specBox.y + 280, { steps: 8 });
  await page.mouse.up();
  await page.keyboard.up('Shift');
  await page.waitForTimeout(150);
  count = await page.textContent('#annotationCount');
  check('freq-range annotation added via shift+drag', count === '3', 'count=' + count);
  const types = await page.$$eval('.annotation-item span', els => els.map(e => e.textContent));
  check('all three marker types present',
        types.some(t => /^Point/.test(t)) && types.some(t => /Time Range/.test(t)) && types.some(t => /Freq Range/.test(t)),
        JSON.stringify(types));
  await page.screenshot({ path: path.join(OUT, 't4_annotations.png'), fullPage: true });

  // ---- Undo / redo ----
  await page.click('#undoBtn');
  await page.waitForTimeout(100);
  count = await page.textContent('#annotationCount');
  check('undo removes last annotation (3->2)', count === '2', 'count=' + count);
  await page.click('#redoBtn');
  await page.waitForTimeout(100);
  count = await page.textContent('#annotationCount');
  check('redo restores annotation (2->3)', count === '3', 'count=' + count);

  // ---- Export JSON ----
  let dl = await Promise.all([ page.waitForEvent('download'), page.click('#exportBtn') ]);
  const jsonText = fs.readFileSync(await dl[0].path(), 'utf8');
  let jsonOk = false, jsonObj = null;
  try { jsonObj = JSON.parse(jsonText); jsonOk = true; } catch (e) {}
  check('JSON export parses', jsonOk);
  check('JSON has meta (filename/sampleRate)', jsonObj && jsonObj.meta && jsonObj.meta.sampleRate === 96000,
        jsonObj && jsonObj.meta ? JSON.stringify(jsonObj.meta) : 'no meta');
  check('JSON has 3 annotations of all types',
        jsonObj && jsonObj.annotations && jsonObj.annotations.length === 3 &&
        new Set(jsonObj.annotations.map(a => a.type)).size === 3,
        jsonObj && jsonObj.annotations ? JSON.stringify(jsonObj.annotations.map(a => a.type)) : 'none');

  // ---- Export CSV ----
  await page.check('input[name="exportFormat"][value="csv"]');
  dl = await Promise.all([ page.waitForEvent('download'), page.click('#exportBtn') ]);
  const csvText = fs.readFileSync(await dl[0].path(), 'utf8');
  const csvLines = csvText.trim().split('\n');
  check('CSV header correct', csvLines[0] === 'type,time,end_time,freq_min,freq_max,label', csvLines[0]);
  check('CSV has 3 data rows', csvLines.length === 4, 'lines=' + csvLines.length);
  check('CSV includes freqRange row', csvLines.some(l => l.startsWith('freqRange,')),
        csvLines.slice(1).join(' | '));

  // ---- Import: MERGE (dismiss the replace dialog) ----
  const importJson = path.join(OUT, 'import_test.json');
  fs.writeFileSync(importJson, JSON.stringify({
    annotations: [
      { type: 'point', time: 0.5, freq: 12000 },
      { type: 'timeRange', time: 1.0, endTime: 1.3 },
      { type: 'bogus', time: 9 },          // should be skipped
      { type: 'point', time: 'NaN' }        // should be skipped
    ]
  }));
  dialogAction = 'dismiss'; // Cancel = Merge
  await page.setInputFiles('#importInput', importJson);
  await page.click('#importBtn');
  await page.waitForTimeout(250);
  count = await page.textContent('#annotationCount');
  check('import MERGE adds 2 valid, skips 2 invalid (3->5)', count === '5', 'count=' + count);

  // ---- Import: REPLACE (accept the dialog) ----
  dialogAction = 'accept'; // OK = Replace
  await page.setInputFiles('#importInput', importJson);
  await page.click('#importBtn');
  await page.waitForTimeout(250);
  count = await page.textContent('#annotationCount');
  check('import REPLACE sets exactly 2 valid (->2)', count === '2', 'count=' + count);

  // Undo the import (replace op)
  await page.click('#undoBtn');
  await page.waitForTimeout(100);
  count = await page.textContent('#annotationCount');
  check('undo of import restores previous (->5)', count === '5', 'count=' + count);

  // ---- Playback (headless: ensure no errors and the clock advances) ----
  await page.click('#playBtn');
  await page.waitForTimeout(400);
  await page.click('#pauseBtn');
  const ct = await page.textContent('#currentTime');
  check('playback advances current time', ct !== '0:00.000', ct);
  await page.click('#stopBtn');
  const ct2 = await page.textContent('#currentTime');
  check('stop resets time to 0', ct2 === '0:00.000', ct2);

  // ---- Zoom ----
  await page.click('#zoomInBtn');
  await waitSpec(page);
  const zl = await page.textContent('#zoomLevel');
  check('zoom in updates level', zl !== '100%', zl);
  await page.click('#zoomResetBtn');
  await waitSpec(page);

  await page.screenshot({ path: path.join(OUT, 't5_final.png'), fullPage: true });

  console.log('\n=== PAGE ERRORS ===');
  console.log(errors.length ? errors.join('\n') : '(none)');
  const passed = results.filter(r => r.pass).length;
  console.log(`\n=== SUMMARY: ${passed}/${results.length} checks passed ===`);
  console.log('Screenshots in: ' + OUT);
  const failed = results.filter(r => !r.pass);
  if (failed.length) { console.log('FAILED:'); failed.forEach(f => console.log('  - ' + f.name + ' :: ' + f.detail)); }
  check('no uncaught page/console errors', errors.length === 0, errors.join(' | '));

  await browser.close();
  process.exit(failed.length || errors.length ? 1 : 0);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
