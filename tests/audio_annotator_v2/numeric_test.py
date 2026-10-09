"""Numeric checks. Use run.py for configuration and fixture generation."""
from pathlib import Path
import json, time, numpy as np, soundfile as sf
from playwright.sync_api import sync_playwright
from common import ROOT,F,OUT,EXTRA_AUDIO,SAMPLE,MEDIUM,launch,mount,existing
files=existing([SAMPLE,*EXTRA_AUDIO]+sorted(F.glob('ultrasonic_*.wav'))+sorted(F.glob('*.flac'))+[F/'native_768k.wav',F/'native_1536k.wav',F/'sparse_2145MB.wav',F/'sparse_4_8GB_rf64.wav'])
results=[]
with sync_playwright() as p:
 browser=launch(p)
 page=browser.new_page(viewport={'width':1500,'height':1050},accept_downloads=True)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
 mount(page)
 for file in files:
  begun=time.monotonic(); info=sf.info(file);print('START',file.name,flush=True)
  page.locator('#fileInput').set_input_files(str(file))
  try:
   page.wait_for_function('AudioAnnotatorV2.inspect().meta && !AudioAnnotatorV2.inspect().renderPending',timeout=60000)
   state=page.evaluate('AudioAnnotatorV2.inspect()')
   assert state['meta']['sampleRate']==info.samplerate,(state['meta'],info)
   assert state['meta']['frames']==info.frames,(state['meta'],info)
   assert state['meta']['channels']==info.channels
   assert float(page.locator('#displayFreqMax').input_value())==info.samplerate/2
   maxerr=0
   with sf.SoundFile(file) as f:
    for start in [0,info.frames//2,max(0,info.frames-257)]:
     f.seek(start); ref=f.read(min(257,info.frames-start),dtype='float32',always_2d=True)
     for ch in range(info.channels):
      got=np.array(page.evaluate('p=>AudioAnnotatorV2.readNativeSamples(p.start,p.count,p.ch)',{'start':start,'count':len(ref),'ch':ch}),dtype=np.float32)
      err=float(np.max(np.abs(got-ref[:,ch])));maxerr=max(maxerr,err)
      assert err<2e-7,(start,ch,err,got[:5],ref[:5,ch])
     if info.channels>1:
      got=np.array(page.evaluate('p=>AudioAnnotatorV2.readNativeSamples(p.start,p.count,-1)',{'start':start,'count':len(ref)}),dtype=np.float32)
      err=float(np.max(np.abs(got-ref.mean(axis=1))));assert err<2e-7,(start,'mix',err)
   page.locator('#windowSeconds').fill(str(min(.25,info.duration/2)))
   page.locator('#windowSeconds').dispatch_event('change')
   page.wait_for_function('!AudioAnnotatorV2.inspect().renderPending',timeout=60000)
   page.locator('#gotoInput').fill(str(info.duration*.5));page.locator('#gotoBtn').click()
   page.wait_for_function('!AudioAnnotatorV2.inspect().renderPending',timeout=60000)
   state=page.evaluate('AudioAnnotatorV2.inspect()'); assert abs(state['render']['start']-state['start'])<1e-8
   # Playback at the midpoint, source bytes and time clock verified.
   page.locator('#playPauseBtn').click();page.wait_for_timeout(450)
   played=page.evaluate('AudioAnnotatorV2.inspect()');rms=page.evaluate('AudioAnnotatorV2.audioRMS()')
   assert played['playing'] or played['cursor']>=info.duration-1/info.samplerate,page.locator('#status').inner_text()
   if played['playing']: page.locator('#playPauseBtn').click()
   page.wait_for_function('!AudioAnnotatorV2.inspect().renderPending',timeout=60000)
   stats=page.evaluate('AudioAnnotatorV2.diagnostics()')
   assert stats['analysis']['byteCache']<=8*1048576
   assert stats['analysis']['fftCache']<=32*1048576
   assert stats['analysis']['frameCache']<=12*1048576
   assert stats['playback']['byteCache']<=8*1048576
   result={'file':file.name,'size':file.stat().st_size,'rate':info.samplerate,'channels':info.channels,'frames':info.frames,'max_sample_error':maxerr,'outputRate':played['outputRate'],'rms':rms,'elapsed_s':round(time.monotonic()-begun,3),'stats':stats,'status':'PASS'}
  except Exception as e:
   result={'file':file.name,'status':'FAIL','error':str(e),'ui_status':page.locator('#status').inner_text(),'browser_errors':list(errors)}
  results.append(result);print(json.dumps(result),flush=True)
  (OUT/'numeric-results.json').write_text(json.dumps(results,indent=2))
 browser.close()
print('ERRORS',errors)
assert all(r['status']=='PASS' for r in results)
