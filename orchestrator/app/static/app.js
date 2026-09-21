const state={admin:null,operator:null,approver:null,epoch:null,drifted:false};
const $=s=>document.querySelector(s);
async function login(username,password){const r=await fetch('/api/auth/token',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username,password})});if(!r.ok)throw new Error(await r.text());return (await r.json()).access_token}
async function api(path,token,opts={}){const headers={...(opts.headers||{}),Authorization:`Bearer ${token}`};if(opts.body && !(opts.body instanceof FormData))headers['content-type']='application/json';const r=await fetch(path,{...opts,headers});const data=await r.json();if(!r.ok)throw new Error(data.detail||JSON.stringify(data));return data}
async function ensure(){if(!state.admin){state.admin=await login('admin','admin-demo');state.operator=await login('operator','operator-demo');state.approver=await login('approver','approver-demo');$('#identity').textContent='demo roles authenticated'}}
function setResult(text,kind='muted'){const el=$('#result');el.className=`result ${kind}`;el.textContent=text}
function renderDiffs(diffs){
  const box=$('#diffs');
  box.replaceChildren();
  if(!diffs?.length){
    const empty=document.createElement('div');
    empty.className='empty';
    empty.textContent='Expected and observed deployment identities match.';
    box.appendChild(empty);
    return;
  }
  for(const d of diffs){
    const row=document.createElement('div'); row.className='diff';
    const field=document.createElement('b'); field.textContent=d.field; row.appendChild(field);
    const pair=document.createElement('div'); pair.className='pair';
    for(const [label,value] of [['approved',d.expected],['observed',d.observed]]){
      const cell=document.createElement('div');
      const small=document.createElement('small'); small.textContent=label;
      cell.appendChild(small); cell.appendChild(document.createTextNode(value)); pair.appendChild(cell);
    }
    row.appendChild(pair); box.appendChild(row);
  }
}
$('#boot').onclick=async()=>{try{await ensure();state.epoch=await api('/api/demo/bootstrap',state.admin,{method:'POST'});state.drifted=false;$('#approve').disabled=false;$('#drift').disabled=true;$('#execute').disabled=true;$('#metric-state').textContent='DRAFT';$('#metric-pipeline').textContent=state.epoch.pipeline_status.toUpperCase();$('#metric-match').textContent='PENDING';setResult(`Epoch ${state.epoch.id.slice(0,8)} created. Approval will bind fingerprint ${state.epoch.fingerprint.slice(0,14)}…`)}catch(e){setResult(e.message,'fail')}};
$('#approve').onclick=async()=>{try{await api(`/api/epochs/${state.epoch.id}/approve`,state.approver,{method:'POST'});$('#drift').disabled=false;$('#execute').disabled=false;$('#metric-state').textContent='APPROVED';setResult('Approval is now bound to the exact deployment fingerprint. You may execute as-is or inject drift.')}catch(e){setResult(e.message,'fail')}};
$('#drift').onclick=async()=>{try{await api(`/api/demo/drift/${state.epoch.id}`,state.admin,{method:'POST',body:JSON.stringify({field:'artifact_digest',value:'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'})});state.drifted=true;$('#metric-match').textContent='DRIFTED';setResult('Artifact digest changed after approval. The next execution should fail closed.','fail')}catch(e){setResult(e.message,'fail')}};
$('#execute').onclick=async()=>{try{const key=`ui-${Date.now()}-${Math.random().toString(16).slice(2)}`;const r=await api(`/api/epochs/${state.epoch.id}/execute`,state.operator,{method:'POST',body:JSON.stringify({idempotency_key:key})});$('#metric-state').textContent=r.outcome;$('#metric-match').textContent=r.outcome==='EXECUTED'?'MATCH':'BLOCKED';renderDiffs(r.differences);setResult(`${r.outcome}: ${r.reason}`,r.outcome==='EXECUTED'?'pass':'fail')}catch(e){setResult(e.message,'fail')}};

async function runAutoDemo(mode){
  try{
    await ensure();
    state.epoch=await api('/api/demo/bootstrap',state.admin,{method:'POST'});
    $('#metric-state').textContent='DRAFT';
    $('#metric-pipeline').textContent=state.epoch.pipeline_status.toUpperCase();
    await api(`/api/epochs/${state.epoch.id}/approve`,state.approver,{method:'POST'});
    $('#metric-state').textContent='APPROVED';
    if(mode==='drift'){
      await api(`/api/demo/drift/${state.epoch.id}`,state.admin,{method:'POST',body:JSON.stringify({field:'artifact_digest',value:'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'})});
      $('#metric-match').textContent='DRIFTED';
    }
    const r=await api(`/api/epochs/${state.epoch.id}/execute`,state.operator,{method:'POST',body:JSON.stringify({idempotency_key:`auto-${mode}-0001`})});
    $('#metric-state').textContent=r.outcome;
    $('#metric-match').textContent=r.outcome==='EXECUTED'?'MATCH':'BLOCKED';
    renderDiffs(r.differences);
    setResult(`${r.outcome}: ${r.reason}`,r.outcome==='EXECUTED'?'pass':'fail');
  }catch(e){ setResult(e.message,'fail'); }
}
const autoMode=new URLSearchParams(location.search).get('autodemo');
if(autoMode==='drift'||autoMode==='happy') window.addEventListener('load',()=>runAutoDemo(autoMode));
