'use strict';
const $ = id => document.getElementById(id);
const names = {en:'English',ru:'Russian',es:'Spanish',ja:'Japanese',fr:'French'};
const state = {mode:'voice',busy:false,recording:false,stream:null,context:null,node:null,
  chunks:[],started:0,lastSpeech:0,heardSpeech:false,timer:null,level:0,history:[],current:null};
const audio = $('audioPlayer');

function message(text = '', error = false) {
  $('statusMessage').textContent = text; $('statusMessage').hidden = !text;
  $('statusMessage').classList.toggle('error', error);
}
function busy(value, text) {
  state.busy = value;
  for (const id of ['source','target','swapLanguages','voiceTab','textTab','translateTyped','retranslate','newSession','clearHistory','pauseSeconds']) $(id).disabled = value || state.recording;
  $('recordButton').disabled = value && !state.recording;
  $('playAudio').disabled = value;
  if (text) message(text);
}
async function api(path, body, raw = false) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 125000);
  try {
    const response = await fetch(`/api/${path}`, {method:'POST',signal:controller.signal,
      headers:body instanceof FormData ? {} : {'Content-Type':'application/json'},
      body:body instanceof FormData ? body : JSON.stringify(body)});
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.error || 'The request could not be completed. Please try again.'); }
    return raw ? response : await response.json();
  } catch(error) {
    if (error.name === 'AbortError') throw new Error('This request took too long. Please try again in a moment.');
    if (error instanceof TypeError) throw new Error('Cannot reach the translator. Make sure run-website.cmd is still running.');
    throw error;
  } finally { clearTimeout(timeout); }
}
function setMode(mode) {
  if (state.busy || state.recording) return;
  state.mode = mode;
  for (const type of ['voice','text']) {
    $(type+'Tab').classList.toggle('selected',type===mode);
    $(type+'Tab').setAttribute('aria-selected',String(type===mode));
    $(type+'Panel').hidden = type!==mode;
  }
  if (mode==='text') $('typedText').focus();
}
$('voiceTab').onclick = () => setMode('voice');
$('textTab').onclick = () => setMode('text');
$('typedText').oninput = () => $('charCount').textContent = `${$('typedText').value.length.toLocaleString()} / 3,000`;
$('typedText').onkeydown = event => {if ((event.ctrlKey||event.metaKey)&&event.key==='Enter'&&!state.busy) translateText($('typedText').value);};
$('translateTyped').onclick = () => translateText($('typedText').value);
$('retranslate').onclick = () => translateText($('sourceText').value);
function clearResult() { audio.pause(); audio.removeAttribute('src'); $('audioPlayer').hidden=true; state.current=null; $('resultPanel').hidden=true; message(); }
$('swapLanguages').onclick = () => { const source=$('source').value; $('source').value=$('target').value; $('target').value=source; clearResult(); };
$('source').onchange = $('target').onchange = clearResult;
$('newSession').onclick = () => {if(state.busy||state.recording)return;clearResult();$('typedText').value='';$('typedText').oninput();window.scrollTo({top:0,behavior:'smooth'});};
$('openGuide').onclick = $('privacyInfo').onclick = () => $('guide').showModal();
$('closeGuide').onclick = () => $('guide').close();
$('guide').onclick = event => {if(event.target===$('guide')){const r=$('guide').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)$('guide').close();}};

function renderHistory() {
  $('history').replaceChildren(); $('clearHistory').hidden=!state.history.length;
  if(!state.history.length){ const el=document.createElement('div');el.className='history-empty';el.textContent='Your translations will appear here.';$('history').append(el);return; }
  for(const entry of [...state.history].reverse()) {
    const button=document.createElement('button');button.className='history-entry';
    const title=document.createElement('strong');title.textContent=`${names[entry.source]} → ${names[entry.target]}`;
    const preview=document.createElement('span');preview.textContent=entry.original;
    button.append(title,preview);button.onclick=()=>{if(state.busy||state.recording)return;message();$('source').value=entry.source;$('target').value=entry.target;renderResult(entry);$('resultPanel').scrollIntoView({behavior:'smooth',block:'nearest'});};
    $('history').append(button);
  }
}
$('clearHistory').onclick=()=>{if(state.busy||state.recording)return;clearResult();state.history.forEach(e=>{if(e.audioUrl)URL.revokeObjectURL(e.audioUrl);});state.history=[];renderHistory();};
function renderResult(entry) {
  if(state.current!==entry)audio.pause();state.current=entry;
  $('sourceText').value=entry.original;$('translatedText').textContent=entry.translation;
  $('translatedText').lang=entry.target;$('sourceText').lang=entry.source;
  $('originalLabel').textContent=`YOUR WORDS · ${names[entry.source].toUpperCase()}`;
  $('translatedLabel').textContent=names[entry.target].toUpperCase();
  $('resultTime').textContent=entry.time;
  $('voiceNote').textContent=entry.fallback?'Multilingual voice':'';
  $('downloadAudio').hidden=!entry.audioUrl;
  $('audioPlayer').hidden=!entry.audioUrl;
  if(entry.audioUrl){audio.src=entry.audioUrl;$('downloadAudio').href=entry.audioUrl;$('downloadAudio').download=`parla-${entry.target}.mp3`;}
  else{audio.removeAttribute('src');$('downloadAudio').removeAttribute('href');}
  $('resultPanel').hidden=false;
}
async function translateText(text) {
  if(state.busy||state.recording)return;
  text=text.trim();if(!text){message('Add some text or record your voice first.',true);return;}
  audio.pause();busy(true,'Finding the right words…');
  const source=$('source').value,target=$('target').value;
  try{
    const result=await api('translate',{text,source,target});
    const entry={original:text,translation:result.text,source,target,time:new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),audioUrl:null,fallback:false};
    state.history.push(entry);
    if(state.history.length>20){const old=state.history.shift();if(old.audioUrl)URL.revokeObjectURL(old.audioUrl);}
    renderHistory();renderResult(entry);message();
    if($('autoPlay').checked)await speak(entry);
  }catch(error){message(error.message,true);}finally{busy(false);}
}
async function speak(entry) {
  if(!entry.audioUrl){
    message('Giving your words a voice…');
    const response=await api('speech',{text:entry.translation,target:entry.target},true);
    entry.audioUrl=URL.createObjectURL(await response.blob());
    entry.fallback=response.headers.get('X-Voice-Fallback')==='true';renderResult(entry);
  }
  message();
  try{await audio.play();}catch{message('Your audio is ready. Press Listen or use the player below.');}
}
$('playAudio').onclick=async()=>{
  if(state.busy||!state.current)return;
  if(!audio.paused){audio.pause();return;}
  busy(true);try{await speak(state.current);}catch(error){message(error.message,true);}finally{busy(false);}
};
audio.onplay=()=>{$('playAudio').querySelector('span').textContent='Pause';};
audio.onpause=audio.onended=()=>{$('playAudio').querySelector('span').textContent='Listen';};
$('copyText').onclick=async()=>{try{await navigator.clipboard.writeText(state.current.translation);message('Translation copied.');}catch{message('Select the translated text and copy it using Ctrl+C.',true);}};

function encodeWav(chunks,rate) {
  const size=chunks.reduce((total,c)=>total+c.length,0);
  const buffer=new ArrayBuffer(44+size*2),view=new DataView(buffer);
  const write=(offset,text)=>{for(let i=0;i<text.length;i++)view.setUint8(offset+i,text.charCodeAt(i));};
  write(0,'RIFF');view.setUint32(4,36+size*2,true);write(8,'WAVE');write(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,rate,true);view.setUint32(28,rate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  write(36,'data');view.setUint32(40,size*2,true);
  let offset=44;for(const chunk of chunks)for(const sample of chunk){const s=Math.max(-1,Math.min(1,sample));view.setInt16(offset,s<0?s*32768:s*32767,true);offset+=2;}
  return new Blob([buffer],{type:'audio/wav'});
}
async function releaseMic(){
  clearInterval(state.timer);state.stream?.getTracks().forEach(track=>track.stop());
  if(state.node){state.node.port.onmessage=null;state.node.disconnect();}
  if(state.context&&state.context.state!=='closed')await state.context.close();
  state.stream=null;state.context=null;state.node=null;state.level=0;
}
function resetRecorder(){
  state.recording=false;$('voicePanel').classList.remove('recording');
  $('recordButton').setAttribute('aria-label','Start recording');
  $('recordingBadge').textContent='YOUR NEXT CONVERSATION STARTS HERE';
  $('recordTitle').textContent='A simple hello goes a long way.';
  $('recordHint').textContent="Tap the microphone and say what's on your mind.";
}
async function startRecording(){
  if(state.busy||state.recording)return;
  if(!navigator.mediaDevices?.getUserMedia){message('Microphone access requires localhost or HTTPS. You can still use Text mode.',true);return;}
  audio.pause();busy(true,'Waiting for microphone permission…');
  try{
    state.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
    state.context=new AudioContext();await state.context.resume();
    await state.context.audioWorklet.addModule('/assets/recorder.js');
    state.node=new AudioWorkletNode(state.context,'parla-recorder');
    const source=state.context.createMediaStreamSource(state.stream);source.connect(state.node);state.node.connect(state.context.destination);
    state.chunks=[];state.started=performance.now();state.lastSpeech=state.started;state.heardSpeech=false;state.recording=true;
    state.node.port.onmessage=event=>{
      if(!state.recording)return;state.chunks.push(event.data);
      state.level=Math.sqrt(event.data.reduce((sum,v)=>sum+v*v,0)/event.data.length);
      if(state.level>.012){state.heardSpeech=true;state.lastSpeech=performance.now();}
    };
    $('voicePanel').classList.add('recording');$('recordButton').setAttribute('aria-label','Stop recording');
    $('recordingBadge').textContent='LISTENING TO YOUR WORLD';$('recordTitle').textContent='Go on. We’re listening.';
    $('recordHint').textContent='Pause to finish, or tap the microphone again.';busy(false);message();
    state.timer=setInterval(()=>{
      const now=performance.now(),elapsed=(now-state.started)/1000,pause=Number($('pauseSeconds').value);
      $('recordTimer').textContent=`00:${String(Math.min(30,Math.floor(elapsed))).padStart(2,'0')} / 00:30`;
      if(elapsed>=30||(state.heardSpeech&&pause>0&&now-state.lastSpeech>pause*1000))stopRecording();
      else if(elapsed>=10&&!state.heardSpeech)stopRecording(true);
    },100);
  }catch(error){await releaseMic();resetRecorder();busy(false);message(error.name==='NotAllowedError'?'Microphone permission was denied. Allow it in your browser, or switch to Text.':error.name==='NotFoundError'?'No microphone was found. Connect one, or switch to Text.':'Could not start the microphone. Close other recording apps and try again.',true);}
}
async function stopRecording(noSpeech=false){
  if(!state.recording)return;state.recording=false;clearInterval(state.timer);busy(true);
  const blob=encodeWav(state.chunks,state.context.sampleRate),source=$('source').value;
  await releaseMic();resetRecorder();busy(true,'Turning your voice into words…');
  if(noSpeech){busy(false);message('No speech detected. Check your microphone, or type your message.',true);return;}
  try{
    const form=new FormData();form.append('audio',blob,'recording.wav');form.append('source',source);
    const result=await api('transcribe',form);$('typedText').value=result.text;$('typedText').oninput();
    busy(false);await translateText(result.text);
  }catch(error){busy(false);message(error.message,true);}
}
$('recordButton').onclick=()=>state.recording?stopRecording():startRecording();
window.addEventListener('beforeunload',()=>{state.stream?.getTracks().forEach(t=>t.stop());});

// Ambient waveform becomes responsive to the microphone's actual amplitude.
const canvas=$('waveform'),ctx=canvas.getContext('2d');
function drawWave(time){
  ctx.clearRect(0,0,800,140);const amplitude=state.recording?Math.min(46,5+state.level*300):5;
  for(let i=0;i<85;i++){
    const x=20+i*9;if(x>315&&x<485)continue;
    const envelope=Math.sin(Math.PI*i/85);
    const height=3+Math.abs(Math.sin(i*.79+time/(state.recording?170:2000)))*amplitude*envelope;
    ctx.fillStyle=state.recording?'#b95438':'#b6beaa';ctx.fillRect(x,70-height/2,2,height);
  }
  requestAnimationFrame(drawWave);
}requestAnimationFrame(drawWave);
fetch('/api/status').then(r=>{if(!r.ok)throw new Error();return r.json();}).then(data=>{
  $('connection').lastChild.textContent=data.speech_ready?'Ready to connect':'Text translation ready';
  if(!data.speech_ready){$('autoPlay').checked=false;message('Add your ElevenLabs key to .env and restart the server to enable spoken translations.');}
}).catch(()=>{$('connection').classList.add('offline');$('connection').lastChild.textContent='Server offline';message('Start run-website.cmd to connect to your translator.',true);});
