"""Regression checks. Use run.py for configuration and fixture generation."""
from pathlib import Path
import json, time, traceback, numpy as np, soundfile as sf, struct
from playwright.sync_api import sync_playwright
from common import ROOT,F,OUT,EXTRA_AUDIO,SAMPLE,MEDIUM,launch,mount,existing
results=[]
# Extensible WAV with 24 significant bits in a 32-bit container plus odd metadata.
samples=np.array([-8388608,-12345,0,12345,8388607],dtype=np.int32)
fmt=struct.pack('<HHIIHHHHI',65534,1,384000,1536000,4,32,22,24,4)+struct.pack('<IHH8B',1,0,16,128,0,0,170,0,56,155,113)
data=(samples<<8).astype('<i4').tobytes(); body=b'WAVEJUNK'+struct.pack('<I',3)+b'abc\0fmt '+struct.pack('<I',40)+fmt+b'data'+struct.pack('<I',len(data))+data
(F/'extensible_24in32.wav').write_bytes(b'RIFF'+struct.pack('<I',len(body))+body)
with sync_playwright() as p:
 browser=launch(p)
 page=browser.new_page(viewport={'width':1600,'height':1200},accept_downloads=True)
 errors=[];dialogs=[];accept=[True];page.on('pageerror',lambda e:errors.append(str(e)))
 def dialog(d):dialogs.append(d.message);d.accept() if accept[0] else d.dismiss()
 page.on('dialog',dialog);mount(page)
 def wait():page.wait_for_function('AudioAnnotatorV2.inspect().meta&&!AudioAnnotatorV2.inspect().renderPending',timeout=60000)
 def state():return page.evaluate('AudioAnnotatorV2.inspect()')
 def load(path):page.locator('#fileInput').set_input_files(str(path));wait()
 def control(id,value):page.locator('#'+id).fill(str(value));page.locator('#'+id).dispatch_event('change')
 def record(name,fn):
  try:info=fn();results.append({'test':name,'status':'PASS','details':info});print('REG PASS',name,info,flush=True)
  except Exception as e:results.append({'test':name,'status':'FAIL','error':str(e),'traceback':traceback.format_exc()});print('REG FAIL',name,str(e),flush=True)
 def marker_count(n):page.wait_for_function('(n)=>AudioAnnotatorV2.inspect().markers.length===n',arg=n,timeout=10000)
 def export(fmt='json'):
  with page.expect_download() as di:page.locator('#export'+('Json' if fmt=='json' else 'Csv')).click()
  path=OUT/('reg-export.'+fmt);di.value.save_as(path);return path.read_bytes().decode('utf-8')
 def imp(text,fmt='json',mode='replace'):
  page.locator('#importMode').select_option(mode);page.locator('#importInput').set_input_files({'name':'test.'+fmt,'mimeType':'text/plain','buffer':text.encode()});page.locator('#importBtn').click();page.wait_for_timeout(200)
 def fft_check():
  load(F/'ultrasonic_PCM_24.wav');peaks=[];maxerr=0
  for ch,expected in [(0,100000),(1,150000)]:
   d=page.evaluate('([t,n,ch])=>AudioAnnotatorV2.readSpectrum(t,n,ch)',[.5,8192,ch]);db=np.array(d['db']);peak=int(db.argmax())*d['sampleRate']/8192;assert abs(peak-expected)<d['sampleRate']/8192;peaks.append(peak)
   # Diagnostic uses the same centered Hann kernel as the visualization.
   with sf.SoundFile(F/'ultrasonic_PCM_24.wav') as f:f.seek(round(.5*f.samplerate)-4096);a=f.read(8192,dtype='float32',always_2d=True)[:,ch]
   w=np.hanning(8192);amp=np.abs(np.fft.rfft(a*w))*2/w.sum();amp[[0,-1]]/=2;reference=20*np.log10(np.maximum(amp,1e-9));error=float(np.max(np.abs(db-reference)));maxerr=max(maxerr,error);assert error<.002,error
  page.locator('#channel').select_option('1');wait();page.locator('#channel').select_option('-1');wait();assert page.locator('#channel').input_value()=='-1'
  return {'ultrasonic_peaks_hz':peaks,'max_fft_error_db':maxerr}
 record('Native ultrasonic FFT matches NumPy; channel/mix UI',fft_check)
 def extensible():
  load(F/'extensible_24in32.wav');actual=page.evaluate('AudioAnnotatorV2.readNativeSamples(0,5)');assert np.array_equal(actual,(samples.astype(np.float64)/8388608).astype(np.float32));return actual
 record('Extensible PCM with valid bits and odd padded metadata',extensible)
 def overview():
  load(MEDIUM);page.locator('#fitBtn').click();wait();assert state()['render']['mode']=='sampled';page.locator('#overviewBtn').click();page.wait_for_function('AudioAnnotatorV2.inspect().overview.complete',timeout=60000);wait();assert state()['render']['mode']=='indexed';d=page.evaluate('AudioAnnotatorV2.diagnostics()');assert d['analysis']['overviewBytes']<=65536*8
  load(F/'sparse_4_8GB_rf64.wav');page.locator('#overviewBtn').click();page.wait_for_timeout(500);page.locator('#overviewBtn').click();page.wait_for_timeout(100);s=state();assert not s['overview']['active'];position=s['overview']['progress'];page.wait_for_timeout(120);assert not state()['overview']['active'];page.locator('#overviewBtn').click();page.wait_for_timeout(500);assert state()['overview']['progress']>=position;page.locator('#overviewBtn').click();return {'exact_index_bytes':d['analysis']['overviewBytes'],'pause_progress':position}
 record('Exact overview completes; large-file pause/resume',overview)
 def hostile_text():
  load(SAMPLE);page.locator('#labelInput').fill('line1\n=SUM(1,2), "quoted" 海豚 <img src=x onerror=alert(1)>');page.locator('#tagInput').fill('=DANGER');page.locator('#addPointBtn').click();marker_count(1);o=json.loads(export());m=o['markers'][0];m['id']='=CMD("x")';m['createdAt']='+Untrusted';m['label']='line1\r\n=SUM(1,2), "quoted" 海豚 <img src=x onerror=alert(1)>';imp(json.dumps(o));marker_count(1);before=json.loads(export());page.locator('#markerRows button').first.click();page.locator('#saveMarker').click();assert state()['markers'][0]['label']==m['label'];csv=export('csv');assert "'=CMD" in csv and "'+Untrusted" in csv;imp(csv,'csv');marker_count(1);after=json.loads(export());assert before['markers']==after['markers'] and before['tags']==after['tags'];assert not page.locator('img').count();return {'multiline_and_unicode_roundtrip':True,'formula_prefixes':True}
 record('CSV multiline/Unicode/formula safety and plain-text DOM',hostile_text)
 def cancel_import():
  before=state()['markers'];o=json.loads(export());o['markers'][0]['label']='replacement';accept[0]=False;imp(json.dumps(o));accept[0]=True;assert state()['markers']==before
  o['meta']['filename']='not_this_audio.wav';accept[0]=False;imp(json.dumps(o),'json','merge');accept[0]=True;assert state()['markers']==before;return {'replace_and_mismatch_cancelled':True}
 record('Cancel replace and mismatched import preserve existing state',cancel_import)
 def keyboard():
  page.locator('#clearBtn').click();marker_count(0);page.locator('#tagInput').fill('');page.locator('input[name=mode][value=point]').check();page.locator('#waveOverlay').click(position={'x':170,'y':70});marker_count(1);page.keyboard.press('Delete');marker_count(0);page.keyboard.press('Control+z');marker_count(1);page.keyboard.press('Control+Shift+z');marker_count(0);page.locator('#waveOverlay').click(position={'x':170,'y':70});marker_count(1);page.locator('#waveOverlay').click(position={'x':170,'y':70},modifiers=['Shift']);marker_count(0)
  page.locator('#waveOverlay').click(position={'x':4,'y':4});marker_count(0);page.locator('input[name=mode][value=time_range]').check();box=page.locator('#waveOverlay').bounding_box();page.mouse.move(box['x']+180,box['y']+70);page.mouse.down();page.mouse.move(box['x']+240,box['y']+70);page.keyboard.press('Escape');page.mouse.up();marker_count(0);return {'delete_shift_delete_undo_redo_escape':True}
 record('Keyboard deletion/history, hit bounds, Escape cancel',keyboard)
 def invalid_audio():
  for name,content in [('truncated.wav',b'RIFF\x40\x00\x00\x00WAVEfmt '),('unsupported.mp3',b'not audio')]:
   page.locator('#fileInput').set_input_files({'name':name,'mimeType':'audio/wav','buffer':content});page.wait_for_function("document.getElementById('status').textContent.startsWith('Cannot open')");assert state()['meta'] is None and page.locator('#playPauseBtn').is_disabled()
  load(SAMPLE);return {'recovered':True}
 record('Bad/truncated audio rejected; subsequent good file works',invalid_audio)
 def drag_drop():
  b=list((SAMPLE).read_bytes());page.evaluate('''b=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(b)],'dropped.wav',{type:'audio/wav'}));document.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}));}''',b);page.wait_for_function("AudioAnnotatorV2.inspect().file==='dropped.wav'");wait();page.locator('#addPointBtn').click();marker_count(1);o=export();page.locator('#clearBtn').click();marker_count(0);page.evaluate('''text=>{const dt=new DataTransfer();dt.items.add(new File([text],'dropped.json',{type:'application/json'}));document.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}));}''',o);marker_count(1);return {'audio_and_annotation_drop':True}
 record('Actual DataTransfer audio and annotation drag/drop',drag_drop)
 def responsive():
  load(F/'large_noise_7min.flac');page.evaluate('''()=>{window.tickGaps=[];window.lastTick=performance.now();window.tickTimer=setInterval(()=>{const now=performance.now();tickGaps.push(now-lastTick);lastTick=now;},16);}''');page.locator('#fitBtn').click();wait();page.wait_for_timeout(300);gaps=page.evaluate('''()=>{clearInterval(tickTimer);return tickGaps;}''');assert len(gaps)>20;info={'max_timer_gap_ms':round(max(gaps),1),'p95_timer_gap_ms':round(float(np.quantile(gaps,.95)),1),'timer_samples':len(gaps),'render_ms':state()['render']['elapsedMs']};assert max(gaps)<1000
  page.set_viewport_size({'width':480,'height':900});wait();assert page.evaluate('document.documentElement.scrollWidth')<=480;page.screenshot(path=str(OUT/'ui-mobile.png'),full_page=True);page.set_viewport_size({'width':1600,'height':1200});wait();return info
 record('Large FLAC main-thread responsiveness and mobile layout',responsive)
 def rapid_load_play():
  for path in [F/'native_1536k.wav',SAMPLE,F/'ultrasonic_PCM_24.wav']:
   load(path);page.locator('#playPauseBtn').evaluate('(e)=>{e.click();e.click();}');page.wait_for_timeout(150);page.locator('#stopBtn').click();assert not state()['playing']
  for _ in range(4):
   page.locator('#fileInput').set_input_files(str(F/'large_noise_7min.flac'));page.locator('#fileInput').set_input_files(str(SAMPLE))
  wait();assert state()['file']=='251006_001_0002.WAV';page.locator('#playPauseBtn').click();page.wait_for_timeout(500);assert state()['playing'] and state()['cursor']>0;page.locator('#stopBtn').click();return {'final_native_rate':state()['meta']['sampleRate'],'scheduled_after_stop':state()['scheduledNodes']}
 record('Rapid native-rate changes, double play, file replacement',rapid_load_play)
 def playback_signal():
  page.evaluate("""()=>{const original=AudioContext.prototype.createAnalyser;AudioContext.prototype.createAnalyser=function(){const a=original.call(this);window.lastAudioAnalyser=a;return a;};}""")
  load(F/'native_1536k.wav');page.locator('#speed').select_option('0.025');page.locator('#playPauseBtn').click();page.wait_for_timeout(500)
  measured=page.evaluate("""()=>{const a=lastAudioAnalyser;a.fftSize=8192;const x=new Float32Array(a.frequencyBinCount);a.getFloatFrequencyData(x);let peak=0;for(let i=1;i<x.length;i++)if(x[i]>x[peak])peak=i;return{peakHz:peak*a.context.sampleRate/a.fftSize,outputRate:a.context.sampleRate};}""")
  # FFT size change clears analyser history; let it collect a fresh window.
  page.wait_for_timeout(350)
  measured=page.evaluate("""()=>{const a=lastAudioAnalyser;const x=new Float32Array(a.frequencyBinCount);a.getFloatFrequencyData(x);let peak=0;for(let i=1;i<x.length;i++)if(x[i]>x[peak])peak=i;return{peakHz:peak*a.context.sampleRate/a.fftSize,outputRate:a.context.sampleRate};}""")
  assert abs(measured['peakHz']-10000)<20,measured
  before=page.evaluate('AudioAnnotatorV2.audioRMS()');page.locator('#volume').evaluate("e=>{e.value='-24';e.dispatchEvent(new Event('input'));}");page.wait_for_timeout(400);after=page.evaluate('AudioAnnotatorV2.audioRMS()');ratio=after/before;assert .20<ratio<.31,ratio
  page.locator('#stopBtn').click();measured['volume_amplitude_ratio']=ratio;return measured
 record('Actual Web Audio graph: ultrasonic slowdown and volume',playback_signal)
 def corrupted_flac():
  raw=bytearray((F/'flac_residuals.flac').read_bytes());raw[-1]^=1
  page.locator('#fileInput').set_input_files({'name':'bad-crc.flac','mimeType':'audio/flac','buffer':bytes(raw)});page.wait_for_function('AudioAnnotatorV2.inspect().meta!==null');page.wait_for_function("document.getElementById('status').textContent.includes('CRC')",timeout=60000)
  assert 'CRC' in page.locator('#status').inner_text();load(SAMPLE);return {'crc_error_reported':True,'recovery':True}
 record('FLAC CRC corruption is reported, not silently decoded',corrupted_flac)
 (OUT/'regression-results.json').write_text(json.dumps({'browser':browser.version,'results':results,'pageerrors':errors},indent=2));browser.close()
 assert not errors,errors
 assert all(r['status']=='PASS' for r in results)
