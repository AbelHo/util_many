// Run: node helper/audio_annotatorv2.html/overview_storage_test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const worker = fs.readFileSync(path.join(__dirname,'../../audio_annotatorv2.html'),'utf8').match(/<script id="audio-worker"[^>]*>([\s\S]*?)<\/script>/)[1];
const frames=65537, sampleRate=16000;
const file=new File([new Uint8Array(frames*2)],'overview-test.wav',{lastModified:1234});
const source={frames,sampleRate,channels:2,format:'PCM16',file,bytes:{cache:{bytes:0},readBytes:0},
    async read(start,count) {return Float32Array.from({length:count},(_,i)=>start+i===65536?.75:0);} };
const events=[], records=new Map(); let storageCalls=0, failSave=false, releaseGet=null;
async function storage(operation,key,record) {
    storageCalls++;
    if(operation==='get') {if(releaseGet) await new Promise(resolve=>{releaseGet=resolve;}); return records.get(key);}
    if(failSave) throw Error('QuotaExceededError');
    records.set(key,record);
}
const ctx=vm.createContext({console,performance,setTimeout,clearTimeout,self:{},testSource:source,crypto:webcrypto,
    TextEncoder,postMessage:m=>events.push(m),testStorage:storage});
vm.runInContext(worker+'\nsource=testSource; overviewStorage=testStorage;',ctx);
const api=vm.runInContext('({createOverview, overviewLoop, overviewBytes, overviewVictims, validOverviewRecord, saveOverview, selectOverview, recordingOverviewKey, openOverviewDB})',ctx);
const current=()=>vm.runInContext('overview',ctx);
async function main() {
    await assert.rejects(api.openOverviewDB(),/unavailable/);
    const key=await api.recordingOverviewKey(); assert.match(key,/^[0-9a-f]{64}$/);
    assert.equal(await api.recordingOverviewKey(),key);
    source.file=new File([new Uint8Array(frames*2)],'overview-test.wav',{lastModified:1235});
    vm.runInContext('overviewIdentity=null;',ctx); assert.notEqual(await api.recordingOverviewKey(),key);
    const altered=new Uint8Array(frames*2); altered[0]=42;
    source.file=new File([altered],'overview-test.wav',{lastModified:1234});
    vm.runInContext('overviewIdentity=null;',ctx); assert.notEqual(await api.recordingOverviewKey(),key);
    source.file=file; vm.runInContext('overviewIdentity=null;',ctx);
    console.log('PASS bounded content fingerprint distinguishes metadata and sampled-content changes; missing storage is optional');

    vm.runInContext('overview=createOverview(0,32); overview.active=true; overviewToken=1;',ctx);
    await api.overviewLoop(1); const built=current(); assert(built.complete);
    built.remember=true; await api.saveOverview(built);
    assert.equal(records.size,1); assert.equal(built.storage,'Saved locally');
    const stored=[...records.values()][0];
    assert(api.validOverviewRecord(stored,0,32));
    assert(!api.validOverviewRecord({...stored,version:999},0,32));
    assert(!api.validOverviewRecord({...stored,frames:frames+1},0,32));
    assert(!api.validOverviewRecord(stored,1,32)); assert(!api.validOverviewRecord(stored,0,64));
    assert(!api.validOverviewRecord({...stored,bytes:stored.bytes+1},0,32));
    assert(!api.validOverviewRecord({...stored,specLevels:stored.specLevels.slice(1)},0,32));
    const old=stored.specLevels[0].peaks[0]; stored.specLevels[0].peaks[0]=-32768;
    assert(!api.validOverviewRecord(stored,0,32)); stored.specLevels[0].peaks[0]=old;
    vm.runInContext('overview=null;',ctx);
    const restored=await api.selectOverview(0,32,true);
    assert.equal(restored.complete,true); assert.match(restored.storage,/Restored/);
    assert.equal(current().waveLevels,stored.waveLevels); assert.equal(current().specLevels,stored.specLevels);
    const offCalls=storageCalls; const off=await api.selectOverview(0,32,false);
    assert.equal(storageCalls,offCalls); assert.equal(off.complete,false); assert.equal(off.waveReady,true);
    console.log('PASS saved summary validation, completed restore, corruption/settings rejection, disabled persistence and waveform reuse');

    const rows=Array.from({length:8},(_,i)=>({key:String(i),bytes:16*1048576,updated:i}));
    assert.deepEqual(Array.from(api.overviewVictims(rows,'new',16*1048576)),['0']);
    assert.deepEqual(Array.from(api.overviewVictims(rows,'new',20*1048576)),['0','1']);
    assert.deepEqual(Array.from(api.overviewVictims(rows,'0',16*1048576)),[]);
    assert.throws(()=>api.overviewVictims([], 'too-big',129*1048576),/budget/);
    ctx.restoredOverview=built; vm.runInContext('overview=restoredOverview;',ctx);
    failSave=true; await api.saveOverview(built); assert.match(built.storage,/Memory only: QuotaExceededError/);
    failSave=false;
    releaseGet=true; const stale=api.selectOverview(0,32,true);
    while(typeof releaseGet !== 'function') await new Promise(r=>setTimeout(r,1));
    await api.selectOverview(1,32,false);
    const release=releaseGet; releaseGet=null; release();
    assert.equal((await stale).stale,true); assert.equal(current().channel,1);
    console.log('PASS eight-entry/128 MiB eviction, storage-failure fallback and stale asynchronous restore isolation');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
