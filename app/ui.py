"""The single page UI. Plain HTML/CSS/JS, no build step, no CDN.

Scoring happens here, in the browser: the server sends counts only, so flipping
between +2/-1/3 and +2/-0.5 is instant and costs zero requests.
"""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d1117">
<title>SSC Marks — response sheet analyser</title>
<style>
:root{
 --bg:#0b0f14; --card:#141a21; --card2:#0f151b; --line:#222c37;
 --tx:#e8eef6; --mut:#8b98a8; --ok:#2ea043; --bad:#f85149; --warn:#d29922;
 --acc:#4c8dff; --acc2:#7ab5ff;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{
 background:radial-gradient(1200px 600px at 50% -10%,#16202c 0%,var(--bg) 55%) fixed;
 color:var(--tx);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
 padding:22px 14px 60px;min-height:100vh;
}
.wrap{max-width:920px;margin:0 auto}
h1{font-size:21px;margin:0 0 4px;letter-spacing:-.2px}
.lead{color:var(--mut);font-size:13px;margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}
label{display:block;font-size:11px;letter-spacing:.8px;text-transform:uppercase;
 color:var(--mut);margin:0 0 7px;font-weight:600}
input,select,button{font:inherit;color:var(--tx)}
input[type=url],input[type=text]{
 width:100%;background:var(--card2);border:1px solid var(--line);border-radius:11px;
 padding:13px 14px;font-size:14px;outline:none;transition:border-color .15s
}
input:focus,select:focus{border-color:var(--acc)}
.row{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap}
.row>div{flex:1 1 160px}
select{width:100%;background:var(--card2);border:1px solid var(--line);
 border-radius:11px;padding:12px 13px;font-size:14px;appearance:none}
.go{margin-top:14px;width:100%;padding:14px;border:0;border-radius:12px;
 background:linear-gradient(180deg,var(--acc2),var(--acc));color:#05101f;
 font-weight:750;font-size:15px;cursor:pointer;letter-spacing:.2px}
.go:disabled{opacity:.55;cursor:not-allowed}
.hint{color:var(--mut);font-size:12px;margin-top:10px}
.err{margin-top:14px;background:#2a1416;border:1px solid #5d2226;color:#ffb8b3;
 border-radius:12px;padding:12px 14px;font-size:13.5px}
.err b{color:#ffd9d6}
/* progress */
.prog{margin-top:16px;display:none}
.prog.on{display:block}
.steps{list-style:none;margin:0;padding:0;font-size:13px}
.steps li{display:flex;gap:9px;padding:5px 0;color:var(--mut);
 animation:in .18s ease-out}
.steps li b{color:var(--tx);font-weight:600;min-width:64px}
.steps li .t{margin-left:auto;font-variant-numeric:tabular-nums;opacity:.6;font-size:12px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--acc);margin-top:7px;flex:none}
@keyframes in{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:none}}
.skel{height:4px;border-radius:99px;background:var(--card2);overflow:hidden;margin-top:12px}
.skel i{display:block;height:100%;width:35%;border-radius:99px;
 background:linear-gradient(90deg,var(--acc),var(--acc2));
 animation:slide 1.15s ease-in-out infinite}
@keyframes slide{0%{margin-left:-35%}100%{margin-left:100%}}
/* results */
#out{margin-top:18px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 14px}
.kpi span{display:block;font-size:10.5px;letter-spacing:.8px;text-transform:uppercase;
 color:var(--mut);font-weight:600}
.kpi b{font-size:23px;letter-spacing:-.4px;line-height:1.25;display:block;
 font-variant-numeric:tabular-nums}
.kpi small{color:var(--mut);font-size:11.5px}
.big{background:linear-gradient(160deg,#17263d,#141a21);border-color:#2b3f5c}
.big b{color:var(--acc2);font-size:29px}
table{width:100%;border-collapse:collapse;margin-top:14px;background:var(--card);
 border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:13.5px}
th,td{padding:11px 10px;text-align:right;border-bottom:1px solid var(--line);
 font-variant-numeric:tabular-nums}
th{font-size:10px;letter-spacing:.7px;text-transform:uppercase;color:var(--mut)}
td:first-child,th:first-child{text-align:left}
tr:last-child td{border-bottom:none}
td.s b{display:block;font-size:13px}
td.s span{color:var(--mut);font-size:11.5px}
.ok{color:var(--ok);font-weight:650}
.bad{color:var(--bad);font-weight:650}
.mut{color:var(--mut)}
.sc{font-weight:750;color:var(--acc2)}
.track{height:4px;background:#1d2631;border-radius:99px;margin-top:5px;overflow:hidden}
.track i{display:block;height:100%;background:linear-gradient(90deg,var(--acc),var(--acc2))}
tr.tot td{background:#101922;font-weight:750;font-size:14.5px}
/* hero ring */
.hero2{display:flex;gap:16px;align-items:center;margin-top:2px;
 background:linear-gradient(155deg,#17263d 0%,#121820 60%,#0f151b 100%);
 border:1px solid #2b3f5c;border-radius:16px;padding:16px 18px;
 box-shadow:0 10px 30px -18px rgba(76,141,255,.55)}
.ringwrap{position:relative;width:110px;height:110px;flex:none}
.ring{width:110px;height:110px;transform:rotate(-90deg)}
.ring .tr2{fill:none;stroke:#1d2631;stroke-width:7}
.ring .pr2{fill:none;stroke:var(--acc2);stroke-width:7;stroke-linecap:round;
 transition:stroke-dashoffset .95s cubic-bezier(.22,.61,.36,1)}
.ringtxt{position:absolute;inset:0;display:flex;flex-direction:column;
 align-items:center;justify-content:center;gap:0}
.ringtxt b{font-size:19px;font-variant-numeric:tabular-nums;letter-spacing:-.4px}
.ringtxt span{font-size:9.5px;letter-spacing:.8px;text-transform:uppercase;color:var(--mut)}
.heroR{flex:1;min-width:0}
.heroR .lbl{display:block;font-size:10.5px;letter-spacing:.8px;
 text-transform:uppercase;color:var(--mut);font-weight:600}
.bigscore{font-size:clamp(28px,7vw,40px);font-weight:800;letter-spacing:-1.2px;
 line-height:1.1;color:var(--acc2);
 background:linear-gradient(180deg,#a8cbff,#4c8dff);-webkit-background-clip:text;
 background-clip:text;-webkit-text-fill-color:transparent}
.heroR small{color:var(--mut);font-size:11.5px}

/* chips */
.sec{margin-top:14px;background:var(--card);border:1px solid var(--line);
 border-radius:14px;padding:13px 14px}
.sec h3{margin:0 0 8px;font-size:12px;letter-spacing:.7px;text-transform:uppercase;color:var(--mut)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:12px;padding:3px 8px;border-radius:8px;background:#1b232d;
 color:var(--mut);border:1px solid var(--line);font-variant-numeric:tabular-nums}
.chip.w{color:#ff9b94;border-color:#40222a;background:#221519}
.chip.s{color:#9aa7b6}
.alt{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.alt div{flex:1 1 150px;background:var(--card2);border:1px solid var(--line);
 border-radius:11px;padding:10px 12px}
.alt span{font-size:11px;color:var(--mut);display:block}
.alt b{font-size:17px;font-variant-numeric:tabular-nums}
.tools{display:flex;gap:9px;margin-top:14px;flex-wrap:wrap}
.tools button{flex:1 1 130px;padding:11px;border-radius:11px;border:1px solid var(--line);
 background:var(--card2);color:var(--tx);cursor:pointer;font-size:13px;font-weight:600}
.tools button:hover{border-color:var(--acc)}
.note{margin-top:12px;font-size:12.5px;color:var(--warn)}
.foot{color:#5c6875;font-size:11.5px;margin-top:22px;text-align:center}
@media (max-width:520px){
 h1{font-size:19px}
 th:nth-child(2),td:nth-child(2){display:none}
 .kpi b{font-size:20px}
 .big b{font-size:25px}
}
</style>
</head>
<body>
<div class="wrap">
 <h1>SSC free marks calculator</h1>
 <p class="lead">response sheet ka link paste karo — section wise + total marks, sahi/galat/chhode sab.</p>

 <div class="card">
  <label for="url">response sheet link</label>
  <input id="url" type="text" inputmode="url" autocomplete="off" spellcheck="false"
   placeholder="https://sscexams.cbexams.com/.../ViewCandResponse.aspx?enckey=...">
  <div class="row">
   <div>
    <label for="scheme">marking scheme</label>
    <select id="scheme"></select>
   </div>
   <div>
    <label for="pc">marks per correct</label>
    <input id="pc" type="text" value="2" inputmode="decimal">
   </div>
   <div>
    <label for="pw">cut per wrong</label>
    <input id="pw" type="text" value="0.5" inputmode="text">
   </div>
  </div>
  <button class="go" id="go">calculate marks</button>
  <p class="hint">green = sahi &nbsp;·&nbsp; red = galat &nbsp;·&nbsp; gray = chhoda</p>
  <div class="prog" id="prog">
   <ul class="steps" id="steps"></ul>
   <div class="skel"><i></i></div>
  </div>
  <div class="err" id="err" style="display:none"></div>
 </div>

 <div id="out"></div>
 <p class="foot">colours seedha official response sheet se padhe jaate hain · koi data store nahi hota</p>
</div>

<script>
const $ = s => document.querySelector(s);
const P = {scheme:'cgl-t1'};
let RESULT = null, POLL = null;

const nf = v => (Math.round(v*100)/100).toLocaleString('en-IN',{maximumFractionDigits:2});

function parseNum(t, dflt){
  t = String(t||'').trim().replace('\u2212','-');
  if(!t) return dflt;
  if(t.includes('/')){ const [a,b]=t.split('/'); const r=parseFloat(a)/parseFloat(b); return isFinite(r)?r:dflt; }
  const r = parseFloat(t); return isFinite(r)?r:dflt;
}

async function loadSchemes(){
  try{
    const r = await fetch('/api/schemes'); const j = await r.json();
    const sel = $('#scheme'); sel.innerHTML='';
    j.presets.forEach(p=>{
      const o=document.createElement('option');
      o.value=p.code; o.textContent=p.label;
      o.dataset.pc=p.per_correct; o.dataset.pw=p.per_wrong;
      sel.appendChild(o);
    });
    const o=document.createElement('option');
    o.value='custom'; o.textContent='custom (neeche apne numbers daalo)';
    sel.appendChild(o);
    sel.value=j.default;
    syncScheme();
  }catch(e){}
}
function syncScheme(){
  const sel=$('#scheme'), opt=sel.selectedOptions[0];
  if(!opt) return;
  if(opt.value==='custom'){ $('#pc').focus(); return; }
  $('#pc').value = opt.dataset.pc;
  $('#pw').value = opt.dataset.pw;
  P.scheme = opt.value;
}
$('#scheme').addEventListener('change', ()=>{
  syncScheme();
  if(RESULT) render(RESULT);
});
['pc','pw'].forEach(id=>$('#'+id).addEventListener('input', ()=>{
  if($('#scheme').value!=='custom'){ $('#scheme').value='custom'; }
  if(RESULT) render(RESULT);
}));

function showErr(msg, hint){
  const e=$('#err'); e.style.display='block';
  e.innerHTML = '<b>'+(msg||'kuch galat hua')+'</b>' + (hint?'<br>'+hint:'');
}
function clearErr(){ $('#err').style.display='none'; }

function pushStep(t, name, detail){
  const li=document.createElement('li');
  li.innerHTML='<div class="dot"></div><b>'+name+'</b><span>'+(detail||'')+
   '</span><span class="t">'+(t!=null?t.toFixed(1)+'s':'')+'</span>';
  $('#steps').appendChild(li);
}

async function go(){
  clearErr();
  const url=$('#url').value.trim();
  if(!url){ showErr('link daalo pehle.'); return; }
  $('#out').innerHTML=''; RESULT=null;
  $('#steps').innerHTML=''; $('#prog').classList.add('on');
  const btn=$('#go'); btn.disabled=true; btn.textContent='calculating…';

  const body={url};
  if($('#scheme').value==='custom'){
    body.correct = parseNum($('#pc').value, 2);
    body.wrong   = parseNum($('#pw').value, 0.5);
  } else { body.scheme = $('#scheme').value; }

  try{
    const r = await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)});
    const j = await r.json();
    if(!r.ok){ showErr(j.error||'request fail', j.hint); reset(); return; }
    poll(j.job_id);
  }catch(e){ showErr('network error', String(e)); reset(); }
}
function reset(){
  $('#prog').classList.remove('on');
  const b=$('#go'); b.disabled=false; b.textContent='calculate marks';
}

async function poll(id){
  let seen=0, tries=0;
  while(tries++ < 30){
    let j;
    try{ j = await (await fetch('/api/job/'+id+'?wait=1&timeout=25')).json(); }
    catch(e){ await new Promise(r=>setTimeout(r,900)); continue; }
    (j.steps||[]).slice(seen).forEach(s=>pushStep(s.t, s.name, s.detail));
    seen=(j.steps||[]).length;
    if(j.status==='done'){ $('#prog').classList.remove('on');
      RESULT=j.result; render(RESULT); reset(); return; }
    if(j.status==='error'){ reset();
      showErr((j.error&&j.error.message)||'kuch galat hua', j.error&&j.error.hint); return; }
  }
  reset(); showErr('bahut time lag raha hai - dusri baar try karo.');
}

function render(res){
  const pc = parseNum($('#pc').value, 2), pw = parseNum($('#pw').value, 0.5);
  const secs = res.sections.map(s=>{
    const marks = s.correct*pc - s.wrong*pw;
    const max = (s.correct+s.wrong+s.skipped+(s.unknown||0))*pc;
    return {...s, marks, max, share: max? Math.max(0,marks/max*100):0};
  });
  const T = secs.reduce((a,s)=>({
    q:a.q+s.correct+s.wrong+s.skipped+(s.unknown||0),
    c:a.c+s.correct, w:a.w+s.wrong, sk:a.sk+s.skipped,
    u:a.u+(s.unknown||0), m:a.m+s.marks, mx:a.mx+s.max
  }),{q:0,c:0,w:0,sk:0,u:0,m:0,mx:0});
  const pct = T.mx? T.m/mx*100 : 0;
  const acc = (T.c+T.w)? T.c/(T.c+T.w)*100 : 0;
  const alts = secs.length && RESULT.alternates ? RESULT.alternates : [];

  const ringC = 214, ringPct = Math.max(0, Math.min(1, pct/100));
  const meta0 = RESULT.meta || {};
  let h='<div class="hero2">';
  h+='<div class="ringwrap"><svg viewBox="0 0 110 110" class="ring">'+
     '<circle class="tr2" cx="55" cy="55" r="34"/>'+
     '<circle class="pr2" cx="55" cy="55" r="34" style="stroke-dasharray:'+ringC+
     ';stroke-dashoffset:'+(ringC*(1-ringPct)).toFixed(1)+'"/></svg>'+
     '<div class="ringtxt"><b>'+(ringPct*100).toFixed(1)+'%</b><span>of max</span></div></div>';
  h+='<div class="heroR"><span class="lbl">final score</span>'+
     '<div class="bigscore">'+nf(T.m)+'</div>'+
     '<small>out of '+nf(T.mx)+' &nbsp;·&nbsp; '+
     (meta0.cached?'cache se':'SSC se '+(meta0.requests||4)+' requests')+'</small></div>';
  h+='</div>';
  h+='<div class="kpis">';
  h+='<div class="kpi"><span>percentage</span><b>'+nf(pct)+'%</b><small>of maximum</small></div>';
  h+='<div class="kpi"><span>correct</span><b class="ok">'+T.c+'</b><small>of '+T.q+' questions</small></div>';
  h+='<div class="kpi"><span>wrong</span><b class="bad">'+T.w+'</b><small>'+nf(T.w*pw)+' marks cut</small></div>';
  h+='<div class="kpi"><span>skipped</span><b>'+T.sk+'</b><small>not attempted</small></div>';
  h+='<div class="kpi"><span>accuracy</span><b>'+nf(acc)+'%</b><small>on '+(T.c+T.w)+' attempted</small></div>';
  h+='</div>';

  h+='<table><thead><tr><th>section</th><th>Q</th><th>correct</th><th>wrong</th>'+
     '<th>skipped</th><th>marks</th><th>max</th></tr></thead><tbody>';
  secs.forEach(s=>{
    h+='<tr><td class="s"><b>'+(s.code||'')+'</b><span>'+s.name+'</span></td>'+
       '<td>'+(s.correct+s.wrong+s.skipped+(s.unknown||0))+'</td>'+
       '<td class="ok">'+s.correct+'</td><td class="bad">'+s.wrong+'</td>'+
       '<td class="mut">'+s.skipped+'</td>'+
       '<td class="sc">'+nf(s.marks)+'<div class="track"><i style="width:'+
        Math.min(100,s.share).toFixed(1)+'%"></i></div></td>'+
       '<td class="mut">'+nf(s.max)+'</td></tr>';
  });
  h+='<tr class="tot"><td>TOTAL</td><td>'+T.q+'</td><td class="ok">'+T.c+'</td>'+
     '<td class="bad">'+T.w+'</td><td class="mut">'+T.sk+'</td>'+
     '<td>'+nf(T.m)+'</td><td>'+nf(T.mx)+'</td></tr></tbody></table>';

  secs.forEach(s=>{
    const w=s.questions_wrong||[], k=s.questions_skipped||[];
    if(!w.length && !k.length) return;
    h+='<div class="sec"><h3>'+(s.code||'')+' · '+s.name+'</h3><div class="chips">';
    w.forEach(q=>h+='<span class="chip w">'+q+'</span>');
    k.forEach(q=>h+='<span class="chip s">'+q+'</span>');
    h+='</div></div>';
  });

  if(alts.length){
    h+='<div class="sec"><h3>same answers, dusri schemes</h3><div class="alt">';
    alts.forEach(a=>{
      h+='<div><span>'+a.label+'</span><b>'+nf(a.marks)+'</b></div>';
    });
    h+='</div></div>';
  }
  (res.notes||[]).forEach(n=>h+='<p class="note">'+n+'</p>');

  const meta = RESULT.meta || {};
  const cost = meta.cached
    ? 'cache se aa gaya — 0 network calls'
    : 'SSC se '+(meta.requests||4)+' requests · '+
      ((meta.elapsed_ms||0)/1000).toFixed(1)+'s';
  h+='<p class="note" style="color:#5c6875">'+cost+'</p>';

  h+='<div class="tools"><button id="copy">copy summary</button>'+
     (navigator.share?'<button id="share">share</button>':'')+
     '<button id="again">naya link</button></div>';

  $('#out').innerHTML=h;
  $('#copy').onclick=()=>copySummary(T,secs,pct,acc);
  const sh=$('#share');
  if(sh) sh.onclick=()=>navigator.share({title:'SSC marks',text:summaryText(T,secs,pct,acc)}).catch(()=>{});
  $('#again').onclick=()=>{ $('#url').value=''; $('#out').innerHTML=''; $('#url').focus(); };
}

function summaryText(T,secs,pct,acc){
  let t='SSC response sheet\n';
  secs.forEach(s=>{ t+=(s.code||'')+' '+s.name+': '+s.correct+'C/'+s.wrong+'W/'+s.skipped+'S -> '+nf(s.marks)+'/'+nf(s.max)+'\n'; });
  t+='TOTAL: '+T.c+'C '+T.w+'W '+T.sk+'S -> '+nf(T.m)+'/'+nf(T.mx)+' ('+nf(pct)+'%)\n';
  t+='accuracy '+nf(acc)+'%';
  return t;
}

function copySummary(T,secs,pct,acc){
  navigator.clipboard.writeText(summaryText(T,secs,pct,acc)).then(()=>{
    const b=$('#copy'); b.textContent='copied'; setTimeout(()=>b.textContent='copy summary',1400);
  });
}

$('#go').onclick=go;
$('#url').addEventListener('keydown', e=>{ if(e.key==='Enter') go(); });
loadSchemes();
</script>
</body></html>
"""
