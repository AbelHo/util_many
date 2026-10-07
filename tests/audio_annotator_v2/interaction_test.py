"""Interaction checks. Use run.py for configuration and fixture generation."""
from pathlib import Path
import json, time, math, traceback
from playwright.sync_api import sync_playwright
from common import ROOT,F,OUT,EXTRA_AUDIO,SAMPLE,MEDIUM,launch,mount,existing
REPORT=OUT/'interaction-results.json'
files=existing([SAMPLE,*EXTRA_AUDIO,F/'large_noise_7min.flac',F/'sparse_2145MB.wav',F/'sparse_4_8GB_rf64.wav',F/'ultrasonic_PCM_24.wav',F/'native_1536k.wav'])
results=[]
with sync_playwright() as p:
 browser=launch(p)
 page=browser.new_page(viewport={'width':1600,'height':1200},accept_downloads=True)
 errors=[];network=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept());page.on('request',lambda r:network.append(r.url))
 mount(page)
 def state():return page.evaluate('AudioAnnotatorV2.inspect()')
 def wait():page.wait_for_function('AudioAnnotatorV2.inspect().meta && !AudioAnnotatorV2.inspect().renderPending',timeout=60000)
 def count(n):page.wait_for_function('(n)=>AudioAnnotatorV2.inspect().markers.length===n',arg=n,timeout=10000)
 def control(id,value):page.locator('#'+id).fill(str(value));page.locator('#'+id).dispatch_event('change')
 def point(canvas,u,v):
  box=page.locator('#'+canvas).bounding_box();return {'x':64+u*(box['width']-80),'y':23+v*(box['height']-51)}
 def click(canvas,u,v,modifiers=None):page.locator('#'+canvas).click(position=point(canvas,u,v),modifiers=modifiers or [])
 def drag(canvas,u1,v1,u2,v2):
  page.locator('#'+canvas).scroll_into_view_if_needed();box=page.locator('#'+canvas).bounding_box();a=point(canvas,u1,v1);b=point(canvas,u2,v2)
  page.mouse.move(box['x']+a['x'],box['y']+a['y']);page.mouse.down();page.mouse.move(box['x']+b['x'],box['y']+b['y'],steps=8);page.mouse.up()
 def download(fmt):
  with page.expect_download() as info:page.locator('#export'+('Json' if fmt=='json' else 'Csv')).click()
  d=info.value;path=OUT/('roundtrip.'+fmt);d.save_as(path);return path.read_bytes().decode('utf-8')
 for index,file in enumerate(files):
  checks=[];start=time.monotonic();print('UI START',file.name,flush=True)
  try:
   page.locator('#fileInput').set_input_files(str(file));wait();s=state();dur=s['meta']['duration'];rate=s['meta']['sampleRate'];ny=rate/2
   assert float(page.locator('#displayFreqMax').input_value())==ny;checks.append('native metadata and Nyquist auto-reset')
   page.locator('#tagInput').fill('');page.locator('#labelInput').fill('Click, "whistle" 海豚 <img src=x onerror=alert(1)>')
   page.locator('input[name=mode][value=point]').check()
   # Uppercase held tag immediately after radio selection, without a priming click.
   page.keyboard.down('Shift');page.keyboard.down('A');click('waveOverlay',.13,.4);page.keyboard.up('A');page.keyboard.up('Shift')
   count(1);assert state()['markers'][0]['tag']=='A';checks.append('held uppercase tag does not trigger shift-delete')
   page.locator('#tagInput').fill('b');click('specOverlay',.72,.31);count(2);assert state()['markers'][1]['frequency'] is not None;checks.append('waveform and frequency-point markers')
   page.locator('input[name=mode][value=time_range]').check();drag('waveOverlay',.44,.5,.23,.5);count(3);m=state()['markers'][-1];assert m['end']>m['start'];checks.append('reversed time-range drag')
   page.locator('input[name=mode][value=frequency_range]').check();drag('specOverlay',.85,.7,.55,.2);count(4);m=state()['markers'][-1];assert 0<=m['freqMin']<m['freqMax']<=ny;checks.append('reversed time-frequency box and native Hz bounds')
   page.locator('#undoBtn').click();count(3);page.locator('#redoBtn').click();count(4);checks.append('undo/redo create operations')
   page.locator('#editLabel').fill('edited, label "quoted" 海豚');page.locator('#saveMarker').click();assert state()['markers'][-1]['label'].startswith('edited');checks.append('selected-marker editor')
   name=page.get_by_label('Name for tag b',exact=True);name.fill('Bottlenose, "whistle"');name.dispatch_event('change')
   color=page.get_by_label('Color for tag b',exact=True);color.fill('#cc3366');color.dispatch_event('change')
   alpha=page.get_by_label('Alpha for tag b',exact=True);alpha.fill('0.45');alpha.dispatch_event('change');assert next(t for t in state()['tags'] if t['key']=='b')['alpha']==.45;checks.append('tag name, color and alpha editing')
   before=json.loads(download('json'));csv=download('csv');assert len(before['markers'])==4 and before['meta']['sampleRate']==rate;checks.append('JSON/CSV downloads with metadata')
   page.locator('#clearBtn').click();count(0);page.locator('#undoBtn').click();count(4);page.locator('#redoBtn').click();count(0);checks.append('clear is undoable and redoable')
   page.locator('#importMode').select_option('replace');page.locator('#importInput').set_input_files({'name':'roundtrip.csv','mimeType':'text/csv','buffer':csv.encode()});page.locator('#importBtn').click();count(4)
   after=json.loads(download('json'));assert before['markers']==after['markers'],(before['markers'],after['markers']);assert before['tags']==after['tags'];checks.append('CSV exact roundtrip, all marker types/tags/colors')
   page.locator('#importMode').select_option('merge');page.locator('#importInput').set_input_files({'name':'merge.json','mimeType':'application/json','buffer':json.dumps(before).encode()});page.locator('#importBtn').click();count(8);assert len({m['id'] for m in state()['markers']})==8;page.locator('#undoBtn').click();count(4);checks.append('JSON merge regenerates colliding IDs; undo restores originals')
   page.locator('#markerFilter').fill('Bottlenose');assert len(page.locator('#markerRows tr').all())==3;page.locator('#markerFilter').fill('');checks.append('filter by tag display name')
   # Malformed file must not partially replace live annotations.
   bad=dict(before);bad['markers']=[dict(m) for m in before['markers']];bad['markers'][2]['end']=float(dur+100)
   page.locator('#importMode').select_option('replace');page.locator('#importInput').set_input_files({'name':'invalid.json','mimeType':'application/json','buffer':json.dumps(bad).encode()});page.locator('#importBtn').click();page.wait_for_function("document.getElementById('status').textContent.includes('outside')");count(4);assert 'outside' in page.locator('#status').inner_text();checks.append('invalid import is atomic')
   control('windowSeconds',min(dur/2,1));wait();initial=state();page.locator('#panRight').click();wait();assert state()['start']>initial['start'];checks.append('window zoom and synchronized pan')
   canvas=page.locator('#specOverlay');canvas.scroll_into_view_if_needed();box=canvas.bounding_box();page.mouse.move(box['x']+box['width']*.6,box['y']+box['height']*.5)
   old=state()['span'];page.keyboard.down('Control');page.mouse.wheel(0,-200);page.keyboard.up('Control');wait();assert state()['span']<old;checks.append('Ctrl+wheel time zoom')
   old=state()['start'];page.mouse.wheel(0,100);wait();assert state()['start']>=old;checks.append('wheel pan')
   page.keyboard.down('Alt');page.mouse.wheel(0,-200);page.keyboard.up('Alt');wait();s=state();assert s['render']['fmax']-s['render']['fmin']<ny;checks.append('Alt+wheel frequency zoom')
   page.locator('#fullBandBtn').click();wait();assert state()['render']['fmax']==ny and state()['render']['fmin']==0
   control('displayFreqMin',ny*2);control('displayFreqMax',-12);wait();band=state()['render'];assert 0<=band['fmin']<band['fmax']<=ny;page.locator('#fullBandBtn').click();wait();checks.append('frequency clamping and full-band restore')
   page.locator('#fftSize').select_option('4096');page.locator('#colorMap').select_option('gray');control('dbMin',-85);control('dbMax',-10);page.locator('#amplitude').select_option('2');wait();assert state()['render']['fft']==4096;assert '0, 0, 0' in page.locator('#frequencyLegend').evaluate('(e)=>e.style.background');checks.append('FFT, color scale, dB limits and amplitude controls')
   # Repeated superseding requests must settle at the last window and FFT.
   page.evaluate('''()=>{for(let i=0;i<25;i++){const a=document.getElementById('windowSeconds');a.value=.12+i*.001;a.dispatchEvent(new Event('change'));const f=document.getElementById('fftSize');f.value=i===24?'8192':'1024';f.dispatchEvent(new Event('change'));}}''');wait();s=state();assert abs(s['span']-.144)<1e-9 and s['render']['fft']==8192 and s['render']['start']==s['start'];checks.append('rapid navigation/settings discard stale renders')
   control('gotoInput',min(.01,dur/4));page.locator('#gotoBtn').click();wait();page.locator('#speed').select_option('0.1');page.locator('#playPauseBtn').click();page.wait_for_timeout(450);a=state();assert a['playing'];page.wait_for_timeout(300);b=state();assert b['cursor']>a['cursor'];page.locator('#playPauseBtn').click();paused=state()['cursor'];page.wait_for_timeout(100);assert abs(state()['cursor']-paused)<1e-8;checks.append('slow playback, time progression and pause stability')
   page.locator('#speed').select_option('1');control('gotoInput',max(0,dur-.04));page.locator('#gotoBtn').click();page.locator('#playPauseBtn').click();page.wait_for_timeout(500);assert not state()['playing'] and abs(state()['cursor']-dur)<1e-6;checks.append('end-of-file playback stops precisely')
   page.locator('#stopBtn').click();assert state()['cursor']==0;checks.append('stop returns to start')
   wait();stats=page.evaluate('AudioAnnotatorV2.diagnostics()');assert stats['analysis']['fftCache']<=32*1048576 and stats['analysis']['byteCache']<=8*1048576;checks.append('bounded cache budgets')
   if index in [0,2,3,7]:
    page.locator('#fitBtn').click();wait();page.screenshot(path=str(OUT/f'ui-{index}.png'),full_page=True)
   results.append({'file':file.name,'status':'PASS','checks':checks,'duration_s':round(time.monotonic()-start,3),'outputRate':state()['outputRate'],'stats':stats})
   print('UI PASS',file.name,len(checks),flush=True)
  except Exception as e:
   results.append({'file':file.name,'status':'FAIL','checks':checks,'error':str(e),'traceback':traceback.format_exc(),'ui_status':page.locator('#status').inner_text(),'state':state()});print('UI FAIL',file.name,str(e),flush=True);page.screenshot(path=str(OUT/f'failed-{index}.png'),full_page=True)
  REPORT.write_text(json.dumps({'browser':browser.version,'results':results,'page_errors':errors,'requests':network},indent=2))
 browser.close()
assert all(r['status']=='PASS' for r in results)
assert not errors
