"""Local-only Mentat 1.0 control center HTML."""

from __future__ import annotations


def render_control_center() -> bytes:
    html = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Mentat Control Center</title>
<style>
:root { font-family: Segoe UI, system-ui, sans-serif; color:#f5f6ff; background:#090b13; }
* { box-sizing:border-box; }
body { margin:0; background:radial-gradient(circle at 15% 0,#202650 0,#0d1020 38%,#090b13 70%); min-height:100vh; }
header { position:sticky; top:0; z-index:2; display:flex; justify-content:space-between; align-items:center; padding:20px 24px; background:#0b0e18eb; border-bottom:1px solid #272d49; backdrop-filter:blur(18px); }
h1 { margin:0; font-size:22px; }
.sub { color:#9fa8cc; font-size:13px; margin-top:4px; }
main { display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:16px; padding:20px; max-width:1500px; margin:auto; }
.card { grid-column:span 4; background:#12172aee; border:1px solid #283151; border-radius:16px; padding:17px; box-shadow:0 20px 50px #0005; }
.card.wide { grid-column:span 8; }
.card.full { grid-column:1/-1; }
h2 { font-size:14px; letter-spacing:.08em; text-transform:uppercase; color:#aeb7df; margin:0 0 13px; }
.value { font-size:28px; font-weight:750; }
.good { color:#69e2af; }
.warn { color:#ffcc73; }
.bad { color:#ff8296; }
.row { display:flex; justify-content:space-between; align-items:center; gap:16px; padding:9px 0; border-top:1px solid #242b45; }
.row:first-of-type { border-top:0; }
.compute { display:grid; grid-template-columns:minmax(180px,1fr) 110px 120px 120px auto; align-items:center; gap:12px; padding:12px 0; border-top:1px solid #242b45; }
.compute:first-of-type { border-top:0; }
small { color:#9aa4c8; }
button { border:0; border-radius:10px; padding:10px 14px; font-weight:700; cursor:pointer; background:#8177ff; color:white; }
button.danger { background:#b84258; }
button.safe { background:#287b62; }
button:disabled { opacity:.55; cursor:not-allowed; }
.gate { border:1px solid #2d3658; border-radius:12px; margin:10px 0; overflow:hidden; }
.gate-title { display:flex; justify-content:space-between; padding:12px; background:#171d34; font-weight:700; }
.requirement { padding:10px 12px; display:grid; grid-template-columns:110px 1fr 105px; gap:10px; border-top:1px solid #252d4b; font-size:13px; }
.badge { display:inline-block; border-radius:99px; padding:3px 8px; background:#272f50; font-size:11px; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; background:#090c17; padding:12px; border-radius:12px; max-height:300px; overflow:auto; color:#bdc6eb; }
@media(max-width:980px) {
  .card,.card.wide { grid-column:1/-1; }
  .compute { grid-template-columns:1fr 1fr; }
  .compute button { grid-column:1/-1; }
}
</style>
</head>
<body>
<header><div><h1>Mentat Control Center</h1><div class="sub">One authority for routing, spending, provider state, and recovery</div></div><button onclick="refresh()">Refresh</button></header>
<main>
<section class="card"><h2>Release</h2><div id="releaseState" class="value">Loading…</div><div id="releasePending" class="sub"></div></section>
<section class="card"><h2>Paid compute</h2><div id="killState" class="value">Loading…</div><div style="margin-top:14px"><button id="killButton" class="danger" onclick="toggleKill()">Enable lockout</button></div></section>
<section class="card"><h2>Exposure</h2><div id="exposure" class="value">—</div><div id="limits" class="sub"></div></section>
<section class="card full"><h2>Active compute</h2><div id="compute"><small>Loading…</small></div></section>
<section class="card wide"><h2>Release gates</h2><div id="gates"></div></section>
<section class="card"><h2>Backends</h2><div id="backends"></div></section>
<section class="card wide"><h2>Saved executions</h2><div id="executions"></div></section>
<section class="card"><h2>Startup recovery</h2><div id="recovery"></div></section>
<section class="card full"><h2>Recent spend events</h2><pre id="events">Loading…</pre></section>
</main>
<script>
let state = null;
function esc(value) { return String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function money(value) { return '$'+Number(value||0).toFixed(2); }
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{'Content-Type':'application/json',...(options.headers||{})}});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error?.message || 'HTTP '+response.status);
  return payload;
}
function row(label,value) { return `<div class="row"><small>${esc(label)}</small><span>${esc(value)}</span></div>`; }
function renderCompute(items) {
  const target=document.getElementById('compute');
  if (!items.length) { target.innerHTML='<small>No active or unresolved compute.</small>'; return; }
  target.innerHTML=items.map(item=>{
    const status=String(item.status||'unknown');
    const canCool=['approved','warming','ready','failed'].includes(status);
    const model=encodeURIComponent(item.model_id);
    return `<div class="compute"><div><strong>${esc(item.model_id)}</strong><div class="sub">Decision ${esc(item.decision_id||'—')}</div></div><span class="badge">${esc(status)}</span><span>${item.hourly_usd==null?'—':money(item.hourly_usd)+'/hr'}</span><small>${esc(item.approved_until||'No expiry')}</small><button class="danger" ${canCool?'':'disabled'} onclick="coolNow('${model}')">Cool now</button></div>`;
  }).join('');
}
function render(value, compute) {
  state=value;
  const release=value.release;
  const ready=release.production_ready;
  document.getElementById('releaseState').className='value '+(ready?'good':'warn');
  document.getElementById('releaseState').textContent=ready?'Production ready':'Release blocked';
  document.getElementById('releasePending').textContent=release.pending.length+' retained evidence requirement(s) remain';
  const kill=value.spend.kill_switch;
  document.getElementById('killState').className='value '+(kill?'bad':'good');
  document.getElementById('killState').textContent=kill?'LOCKED OUT':'Enabled by approval';
  const button=document.getElementById('killButton');
  button.textContent=kill?'Disable lockout':'Enable lockout'; button.className=kill?'safe':'danger';
  document.getElementById('exposure').textContent=money(value.spend.active_reserved_usd)+' reserved';
  document.getElementById('limits').textContent=money(value.spend.today_exposure_usd)+' today · '+money(value.spend.month_exposure_usd)+' this month';
  renderCompute(compute.active_compute||[]);
  document.getElementById('gates').innerHTML=release.gates.map(g=>`<div class="gate"><div class="gate-title"><span>Gate ${g.gate}</span><span class="${g.passed?'good':'warn'}">${g.passed?'Passed':'Pending'}</span></div>${g.requirements.map(r=>`<div class="requirement"><span class="badge">${esc(r.kind)}</span><span>${esc(r.title)}</span><span class="${r.passed?'good':r.status==='failed'?'bad':'warn'}">${esc(r.status)}</span></div>`).join('')}</div>`).join('');
  document.getElementById('backends').innerHTML=value.backends.map(b=>row(b.kind,b.production_eligible?'production eligible':'gated')).join('');
  document.getElementById('executions').innerHTML=value.executions.length?value.executions.map(e=>row(e.execution_id,e.state+' · '+e.model_id)).join(''):'<small>No saved executions.</small>';
  document.getElementById('recovery').innerHTML=value.startup_recovery_plan.length?value.startup_recovery_plan.map(e=>row(e.execution_id,e.action)).join(''):'<small>No unresolved startup recovery.</small>';
  document.getElementById('events').textContent=JSON.stringify(value.spend.recent_events,null,2);
}
async function refresh() {
  try {
    const [status,compute]=await Promise.all([api('/v1/status'),api('/v1/compute')]);
    render(status,compute);
  } catch(error) { alert(error.message); }
}
async function coolNow(model) {
  if (!confirm('Cool this compute now? Mentat will retain the spend reservation until billing is reconciled.')) return;
  await api('/v1/compute/'+model+'/cool',{method:'POST',body:'{}'});
  await refresh();
}
async function toggleKill() {
  if (!state) return;
  const enabled=!state.spend.kill_switch;
  const reason=prompt(enabled?'Reason for emergency paid-compute lockout:':'Reason for re-enabling paid compute:','Operator action');
  if (!reason) return;
  await api('/v1/control/kill-switch',{method:'POST',body:JSON.stringify({enabled,reason})}); await refresh();
}
refresh(); setInterval(refresh,5000);
</script>
</body></html>"""
    return html.encode("utf-8")
