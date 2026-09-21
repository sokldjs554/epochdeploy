const state={admin:null,operator:null,approver:null,epoch:null,drifted:false,view:'release'};
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];

async function login(username,password){
  const r=await fetch('/api/auth/token',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username,password})});
  if(!r.ok)throw new Error(await r.text());
  return (await r.json()).access_token;
}
async function api(path,token,opts={}){
  const headers={...(opts.headers||{}),Authorization:`Bearer ${token}`};
  if(opts.body && !(opts.body instanceof FormData))headers['content-type']='application/json';
  const r=await fetch(path,{...opts,headers});
  const data=await r.json();
  if(!r.ok)throw new Error(data.detail||JSON.stringify(data));
  return data;
}
async function ensure(){
  if(!state.admin){
    state.admin=await login('admin','admin-demo');
    state.operator=await login('operator','operator-demo');
    state.approver=await login('approver','approver-demo');
    $('#identity').textContent='demo roles authenticated';
  }
}
function setResult(text,kind='muted'){const el=$('#result');el.className=`result ${kind}`;el.textContent=text;}
function currentEpochLabel(){return state.epoch?`${state.epoch.project} · ${state.epoch.environment} · ${state.epoch.id.slice(0,8)}`:'No active epoch';}
function syncEpochContext(){
  $$('.epoch-context').forEach(el=>el.textContent=currentEpochLabel());
  const enabled=Boolean(state.epoch);
  $('#upload-evidence').disabled=!enabled;
  $('#refresh-evidence').disabled=!enabled;
  $('#refresh-receipts').disabled=!enabled;
}
function renderDiffs(diffs){
  const box=$('#diffs'); box.replaceChildren();
  if(!diffs?.length){
    const empty=document.createElement('div'); empty.className='empty'; empty.textContent='Expected and observed deployment identities match.'; box.appendChild(empty); return;
  }
  for(const d of diffs){
    const row=document.createElement('div'); row.className='diff';
    const field=document.createElement('b'); field.textContent=d.field; row.appendChild(field);
    const pair=document.createElement('div'); pair.className='pair';
    for(const [label,value] of [['approved',d.expected],['observed',d.observed]]){
      const cell=document.createElement('div');
      const small=document.createElement('small'); small.textContent=label;
      const code=document.createElement('code'); code.textContent=value;
      cell.appendChild(small); cell.appendChild(code); pair.appendChild(cell);
    }
    row.appendChild(pair); box.appendChild(row);
  }
}
function resetControls(){
  $('#verify-pipeline').disabled=true; $('#approve').disabled=true; $('#drift').disabled=true; $('#execute').disabled=true;
  $('#metric-match').textContent='PENDING'; renderDiffs([]);
}

async function bootstrap(){
  await ensure();
  state.epoch=await api('/api/demo/bootstrap',state.admin,{method:'POST'});
  state.drifted=false; resetControls(); syncEpochContext();
  $('#verify-pipeline').disabled=false;
  $('#metric-state').textContent='DRAFT';
  $('#metric-pipeline').textContent=state.epoch.pipeline_status.toUpperCase();
  setResult(`Epoch ${state.epoch.id.slice(0,8)} created with pipeline evidence pending.`);
}
async function verifyPipeline(){
  state.epoch=await api(`/api/demo/gitlab-success/${state.epoch.id}`,state.admin,{method:'POST'});
  $('#metric-pipeline').textContent=state.epoch.pipeline_status.toUpperCase();
  $('#approve').disabled=false;
  setResult(`GitLab Pipeline Hook verified pipeline ${state.epoch.pipeline_id} against commit ${state.epoch.commit_sha.slice(0,12)}…`,'pass');
}
async function approve(){
  await api(`/api/epochs/${state.epoch.id}/approve`,state.approver,{method:'POST'});
  $('#drift').disabled=false; $('#execute').disabled=false; $('#metric-state').textContent='APPROVED';
  setResult('Approval is bound to the exact deployment fingerprint. Execute as-is or inject drift.');
}
async function injectDrift(){
  await api(`/api/demo/drift/${state.epoch.id}`,state.admin,{method:'POST',body:JSON.stringify({field:'artifact_digest',value:'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'})});
  state.drifted=true; $('#metric-match').textContent='DRIFTED';
  setResult('Artifact digest changed after approval. The next execution should fail closed.','fail');
}
async function execute(){
  const key=`ui-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const r=await api(`/api/epochs/${state.epoch.id}/execute`,state.operator,{method:'POST',body:JSON.stringify({idempotency_key:key})});
  $('#metric-state').textContent=r.outcome; $('#metric-match').textContent=r.outcome==='EXECUTED'?'MATCH':'BLOCKED';
  renderDiffs(r.differences); setResult(`${r.outcome}: ${r.reason}`,r.outcome==='EXECUTED'?'pass':'fail');
}

$('#boot').onclick=()=>bootstrap().catch(e=>setResult(e.message,'fail'));
$('#verify-pipeline').onclick=()=>verifyPipeline().catch(e=>setResult(e.message,'fail'));
$('#approve').onclick=()=>approve().catch(e=>setResult(e.message,'fail'));
$('#drift').onclick=()=>injectDrift().catch(e=>setResult(e.message,'fail'));
$('#execute').onclick=()=>execute().catch(e=>setResult(e.message,'fail'));

function textNode(tag,text,className=''){
  const el=document.createElement(tag); if(className)el.className=className; el.textContent=text; return el;
}
function recordRow(label,value,mono=false){
  const row=document.createElement('div'); row.className='kv-row';
  row.appendChild(textNode('span',label)); row.appendChild(textNode(mono?'code':'strong',value??'—'));
  return row;
}
async function loadEvidence(){
  const box=$('#evidence-list'); box.replaceChildren();
  if(!state.epoch){box.appendChild(textNode('div','No active epoch.','empty'));return;}
  await ensure(); const rows=await api(`/api/epochs/${state.epoch.id}/evidence`,state.operator);
  if(!rows.length){box.appendChild(textNode('div','No evidence attached to this epoch.','empty'));return;}
  for(const item of rows){
    const card=document.createElement('div'); card.className='record';
    const top=document.createElement('div'); top.className='record-top'; top.appendChild(textNode('b',item.filename)); top.appendChild(textNode('span',item.kind,'pill')); card.appendChild(top);
    card.appendChild(recordRow('SHA-256',item.sha256,true)); card.appendChild(recordRow('Size',`${item.size_bytes} bytes`)); card.appendChild(recordRow('Type',item.content_type)); box.appendChild(card);
  }
}
async function uploadEvidence(){
  if(!state.epoch)return;
  const input=$('#evidence-file'); const file=input.files[0];
  if(!file){$('#evidence-result').className='result fail';$('#evidence-result').textContent='Choose a file first.';return;}
  await ensure();
  const form=new FormData(); form.append('kind',$('#evidence-kind').value||'evidence'); form.append('file',file);
  const result=await api(`/api/epochs/${state.epoch.id}/evidence`,state.operator,{method:'POST',body:form});
  $('#evidence-result').className='result pass'; $('#evidence-result').textContent=`Attached ${result.filename} · sha256 ${result.sha256.slice(0,16)}…`;
  input.value=''; await loadEvidence();
}
$('#upload-evidence').onclick=()=>uploadEvidence().catch(e=>{$('#evidence-result').className='result fail';$('#evidence-result').textContent=e.message;});
$('#refresh-evidence').onclick=()=>loadEvidence().catch(()=>{});

async function loadReceipts(){
  const box=$('#receipt-list'); box.replaceChildren();
  if(!state.epoch){box.appendChild(textNode('div','Execute a release to generate a receipt.','empty'));return;}
  await ensure(); const rows=await api(`/api/epochs/${state.epoch.id}/receipts`,state.operator);
  if(!rows.length){box.appendChild(textNode('div','No execution receipt exists for this epoch yet.','empty'));return;}
  for(const item of rows){
    const card=document.createElement('div'); card.className=`record receipt ${item.outcome==='EXECUTED'?'receipt-pass':'receipt-fail'}`;
    const top=document.createElement('div'); top.className='record-top'; top.appendChild(textNode('b',item.outcome)); top.appendChild(textNode('span',`${item.latency_ms} ms`,'pill')); card.appendChild(top);
    card.appendChild(textNode('p',item.reason,'record-copy')); card.appendChild(recordRow('Approved',item.expected_fingerprint,true)); card.appendChild(recordRow('Observed',item.observed_fingerprint,true)); box.appendChild(card);
  }
}
$('#refresh-receipts').onclick=()=>loadReceipts().catch(()=>{});

function renderKV(selector,entries){const box=$(selector);box.replaceChildren();for(const [label,value,mono] of entries)box.appendChild(recordRow(label,String(value??'—'),Boolean(mono)));}
async function loadIntegrations(){
  await ensure(); const data=await api('/api/integrations/status',state.operator);
  renderKV('#integration-gitlab',[
    ['Webhook',data.gitlab.webhook_configured?'configured':'missing'],
    ['Event',data.gitlab.event],['Commit SHA binding',data.gitlab.sha_binding?'enforced':'off'],
    ['Last event',data.gitlab.last_event_type||'none'],['Pipeline ID',data.gitlab.last_external_id||'—',true]
  ]);
  renderKV('#integration-executor',[[ 'Mode',data.executor.mode ],['Transport',data.executor.transport],['Request auth',data.executor.request_auth]]);
  renderKV('#integration-database',[[ 'Dialect',data.database.dialect ],['Workflow state','epochs · approvals · receipts'],['Outbox','transactional event record']]);
}
$('#refresh-integrations').onclick=()=>loadIntegrations().catch(()=>{});

async function showView(name){
  state.view=name;
  $$('[data-view-panel]').forEach(el=>el.classList.toggle('hidden',el.dataset.viewPanel!==name));
  $$('.nav').forEach(el=>{const active=el.dataset.view===name;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  syncEpochContext();
  if(name==='evidence')await loadEvidence();
  if(name==='receipts')await loadReceipts();
  if(name==='integrations')await loadIntegrations();
}
$$('.nav').forEach(btn=>btn.addEventListener('click',()=>showView(btn.dataset.view).catch(()=>{})));

async function runAutoDemo(mode){
  try{
    await bootstrap(); await verifyPipeline(); await approve();
    if(mode==='drift')await injectDrift();
    await execute();
  }catch(e){setResult(e.message,'fail');}
}
const autoMode=new URLSearchParams(location.search).get('autodemo');
if(autoMode==='drift'||autoMode==='happy')window.addEventListener('load',()=>runAutoDemo(autoMode));
