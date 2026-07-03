// stress_test.js — robustness & performance checks for audio_annotator.html.
// Verifies that rapid back-to-back control changes converge to the LAST setting
// (the per-pass settings snapshot + recompute-if-changed logic), that a large
// 8192-point FFT renders quickly, and that all four color scales render.
//
// Requires Playwright. Run from anywhere:
//   node helper/audio_annotator.html/stress_test.js
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

let fails = 0;
function check(name, cond, d) { console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${d ? '  — ' + d : ''}`); if (!cond) fails++; }

// cheap signature of the spectrogram canvas, to detect when rendering settled
async function sig(page) {
  return page.evaluate(() => {
    const c = document.getElementById('spectrogramCanvas');
    const { data } = c.getContext('2d').getImageData(0, 0, c.width, c.height);
    let s = 0;
    for (let i = 0; i < data.length; i += 997) s = (s + data[i] * (i % 251 + 1)) % 1e9;
    return s;
  });
}
async function waitStable(page, maxMs = 8000) {
  const t0 = Date.now();
  let prev = await sig(page), stableSince = null;
  while (Date.now() - t0 < maxMs) {
    await page.waitForTimeout(120);
    const cur = await sig(page);
    if (cur === prev) { if (stableSince == null) stableSince = Date.now(); if (Date.now() - stableSince > 250) break; }
    else { stableSince = null; prev = cur; }
  }
  return Date.now() - t0;
}
// brightest pixel rgb in a region
async function brightest(page, x0, y0, x1, y1) {
  return page.evaluate(({ x0, y0, x1, y1 }) => {
    const c = document.getElementById('spectrogramCanvas');
    const { data, width } = c.getContext('2d').getImageData(0, 0, c.width, c.height);
    let best = -1, rgb = [0, 0, 0];
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
      const i = (y * width + x) * 4;
      const lum = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      if (lum > best) { best = lum; rgb = [data[i], data[i + 1], data[i + 2]]; }
    }
    return { lum: best, r: rgb[0], g: rgb[1], b: rgb[2] };
  }, { x0, y0, x1, y1 });
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1300 } });
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });

  await page.goto(HTML);
  await page.setInputFiles('#fileInput', WAV);
  await waitStable(page);

  // --- Convergence: rapid back-to-back color changes settle on the LAST one ---
  await page.selectOption('#colorScaleSelect', 'grayscale');
  await page.selectOption('#colorScaleSelect', 'hot');
  await waitStable(page);
  // 8 kHz tone (~0.9s): x≈360, y≈ height*(1-8000/48000)=333
  let px = await brightest(page, 340, 320, 380, 345);
  // Hot colormap => strong red dominance; grayscale => r≈g≈b
  check('rapid color change converges to HOT (not grayscale)',
        px.r > px.b + 40 && px.r >= px.g, `rgb=(${px.r},${px.g},${px.b}) lum=${px.lum.toFixed(0)}`);

  await page.selectOption('#colorScaleSelect', 'grayscale');
  await waitStable(page);
  px = await brightest(page, 340, 320, 380, 345);
  check('grayscale renders neutral (r≈g≈b)', Math.abs(px.r - px.g) < 12 && Math.abs(px.g - px.b) < 12,
        `rgb=(${px.r},${px.g},${px.b})`);

  // --- Convergence: rapid FFT-size changes settle on the LAST one ---
  await page.selectOption('#colorScaleSelect', 'viridis');
  await waitStable(page);
  await page.selectOption('#fftSizeSelect', '256');
  await page.selectOption('#fftSizeSelect', '8192');
  const elapsed8192 = await waitStable(page, 12000);
  const fftVal = await page.evaluate(() => document.getElementById('fftSizeSelect').value);
  check('FFT select shows 8192 after rapid change', fftVal === '8192', fftVal);
  const std = await page.evaluate(() => {
    const c = document.getElementById('spectrogramCanvas');
    const { data } = c.getContext('2d').getImageData(0, 0, c.width, c.height);
    let s = 0, s2 = 0, n = 0;
    for (let i = 0; i < data.length; i += 16) { const l = data[i]; s += l; s2 += l * l; n++; }
    const m = s / n; return Math.sqrt(s2 / n - m * m);
  });
  check('8192 FFT spectrogram rendered with structure', std > 15, 'std=' + std.toFixed(1));
  check('8192 FFT render time reasonable (<10s)', elapsed8192 < 10000, elapsed8192 + 'ms');
  await page.screenshot({ path: path.join(OUT, 's1_fft8192_viridis.png'), fullPage: true });

  // --- All four colormaps render without error ---
  for (const cs of ['viridis', 'cool', 'grayscale', 'hot']) {
    await page.selectOption('#fftSizeSelect', '2048');
    await page.selectOption('#colorScaleSelect', cs);
    await waitStable(page);
    const ok = await page.evaluate(() => {
      const c = document.getElementById('spectrogramCanvas');
      const { data } = c.getContext('2d').getImageData(0, 0, c.width, c.height);
      let first = data[0], varied = false;
      for (let i = 0; i < data.length; i += 400) if (data[i] !== first) { varied = true; break; }
      return varied;
    });
    check('colormap renders: ' + cs, ok);
  }
  await page.screenshot({ path: path.join(OUT, 's2_hot.png'), fullPage: true });

  console.log('\nERRORS:', errors.length ? errors.join('\n') : '(none)');
  check('no page/console errors during stress', errors.length === 0, errors.join(' | '));
  console.log('Screenshots in: ' + OUT);
  console.log(`\n${fails === 0 ? 'ALL STRESS CHECKS PASSED' : fails + ' STRESS CHECK(S) FAILED'}`);
  await browser.close();
  process.exit(fails || errors.length ? 1 : 0);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
