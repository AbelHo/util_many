// gen_wav.js — generate the bioacoustic-style test recording used by the
// Audio Annotator tests and demo.
//
// Output: 96 kHz, mono, 16-bit PCM, ~3 s. Rich time-frequency content (chirps,
// tones, clicks, harmonics) spanning the full 0–48 kHz band so the spectrogram,
// color scales, FFT sizes, frequency-range selection and annotations can all be
// exercised meaningfully. The high (>24 kHz) content is what proves native
// sample-rate decoding works (a default 44.1 kHz context would discard it).
//
// Usage:
//   node gen_wav.js                       # writes ../../sample/251006_001_0002.WAV
//   node gen_wav.js /path/to/out.WAV      # writes to a custom path
const fs = require('fs');
const path = require('path');

const SR = 96000;
const DUR = 3.0;
const N = Math.floor(SR * DUR);
const data = new Float32Array(N);

// Low-level broadband background noise.
for (let i = 0; i < N; i++) data[i] += (Math.random() * 2 - 1) * 0.012;

// Helper: additive tone over [t0,t1] with optional linear frequency sweep.
function chirp(t0, t1, f0, f1, amp, fade = 0.01) {
  const i0 = Math.floor(t0 * SR), i1 = Math.floor(t1 * SR);
  let phase = 0;
  for (let i = i0; i < i1 && i < N; i++) {
    const u = (i - i0) / (i1 - i0);
    const f = f0 + (f1 - f0) * u;
    phase += (2 * Math.PI * f) / SR;
    // raised-cosine fade in/out to avoid clicks
    const tt = (i - i0) / SR, dur = (i1 - i0) / SR;
    let env = 1;
    if (tt < fade) env = 0.5 * (1 - Math.cos(Math.PI * tt / fade));
    else if (tt > dur - fade) env = 0.5 * (1 - Math.cos(Math.PI * (dur - tt) / fade));
    data[i] += Math.sin(phase) * amp * env;
  }
}

// Broadband click (impulse-ish) at time tc.
function click(tc, amp) {
  const ic = Math.floor(tc * SR);
  for (let k = -40; k <= 40; k++) {
    const i = ic + k;
    if (i < 0 || i >= N) continue;
    const w = Math.exp(-(k * k) / (2 * 8 * 8));
    data[i] += (Math.random() * 2 - 1) * amp * w;
  }
}

// 0.20-0.55s: descending chirp 20kHz -> 5kHz (bird-like sweep)
chirp(0.20, 0.55, 20000, 5000, 0.32);
// 0.80-1.05s: steady tone burst at 8 kHz
chirp(0.80, 1.05, 8000, 8000, 0.30);
// 1.25-1.70s: ascending chirp 2kHz -> 40kHz (exercises the high-frequency band)
chirp(1.25, 1.70, 2000, 40000, 0.30);
// three broadband clicks
click(1.85, 0.5); click(1.95, 0.5); click(2.05, 0.5);
// 2.35-2.85s: two simultaneous tones (10 kHz + 25 kHz)
chirp(2.35, 2.85, 10000, 10000, 0.22);
chirp(2.35, 2.85, 25000, 25000, 0.18);

// Normalize to avoid clipping, leave headroom.
let peak = 0;
for (let i = 0; i < N; i++) peak = Math.max(peak, Math.abs(data[i]));
const norm = peak > 0 ? 0.85 / peak : 1;

// Write 16-bit PCM WAV (canonical 44-byte header).
const bytesPerSample = 2;
const dataSize = N * bytesPerSample;
const buf = Buffer.alloc(44 + dataSize);
buf.write('RIFF', 0); buf.writeUInt32LE(36 + dataSize, 4); buf.write('WAVE', 8);
buf.write('fmt ', 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); // PCM
buf.writeUInt16LE(1, 22);                    // mono
buf.writeUInt32LE(SR, 24);                   // sample rate
buf.writeUInt32LE(SR * bytesPerSample, 28);  // byte rate
buf.writeUInt16LE(bytesPerSample, 32);       // block align
buf.writeUInt16LE(16, 34);                   // bits per sample
buf.write('data', 36); buf.writeUInt32LE(dataSize, 40);
for (let i = 0; i < N; i++) {
  const s = Math.max(-1, Math.min(1, data[i] * norm));
  buf.writeInt16LE(Math.round(s * 32767), 44 + i * 2);
}

const out = process.argv[2] || path.resolve(__dirname, '../../sample/251006_001_0002.WAV');
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, buf);
console.log(`Wrote ${out}: ${SR} Hz, mono, 16-bit, ${DUR}s, ${(buf.length / 1024).toFixed(0)} KB`);
