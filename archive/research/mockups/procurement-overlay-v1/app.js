// Isolated design simulation. No backend calls, model requests, or business writes.
const $ = (selector) => document.querySelector(selector);
const state = { scenario: 'review', preset: 'calm', mode: 'floating', draft: '', evidence: false, terms: false, reconciled: false };
const defaultIntent = 'Prepare a draft order for the packaging sleeve shortage. Keep it under $1,200 and have it here by 16 October.';
let intent = defaultIntent;
const escapeHTML = (value) => value.replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const statuses = { ready:'Ready to help', working:'Checking context', clarify:'Your input needed', review:'Review needed', executing:'Approval recorded', verifying:'Checking result', uncertain:'Outcome unknown', verified:'Verified · demo', stale:'Review expired', rejected:'Draft declined', cancelled:'Task stopped' };
const userMessage = () => `<div class="user-message"><div class="user-label"><span>You</span><span>09:41 · demo</span></div>${escapeHTML(intent)}</div>`;
const assistantLabel = () => `<div class="assistant-label"><span class="mini-spark">✳</span>e-agent <span class="ai-tag">AI</span><span class="status ${state.scenario === 'verified' ? 'green' : ''}">${statuses[state.scenario]}</span></div>`;
const artifact = (saved = false) => `<article class="artifact" aria-label="${saved ? 'Saved draft order' : 'Proposed purchase order'}"><div class="artifact-head"><span class="document-icon">▤</span><div><b>Purchase order</b><small>${saved ? 'Saved draft · PO-DEMO-0084' : 'New draft · Proposal 003'}</small></div><span class="draft-badge">Draft</span></div><div class="artifact-body"><div class="supplier-line"><b>Northline Paper</b><small>✓ Approved supplier</small></div><div class="line-item"><span>Packaging sleeves</span><strong>$1,080.00</strong><small>240 units × $4.50</small><small>USD · tax-free fixture</small></div><div class="artifact-meta"><div><span>Needed by</span>16 Oct 2026</div><div><span>Deliver to</span>Central warehouse</div></div><div class="budget"><span>$1,200.00 budget</span><b>$120.00 within budget</b></div><div class="budget-track"><i></i></div></div><div class="evidence-summary"><span class="check">✓</span><b>Matches the 240-unit shortage.</b> Selected offer meets your budget and requested date in this fixture.</div></article>`;
const evidence = () => `<details class="disclosure" id="evidence" ${state.evidence || state.preset === 'operator' ? 'open' : ''}><summary>Why this proposal?<span>3 sources</span></summary><div class="evidence-item"><b>Inventory snapshot · INV-104 / rev 18</b>Demand 400 units − available 160 = shortage 240.<br><small>Central warehouse · 8 Oct, 09:41 ICT · complete fixture</small></div><div class="evidence-item"><b>Supplier offer · OFF-042 / rev 6</b>Northline Paper · $4.50 per unit · delivery by 16 Oct.<br><small>8 Oct, 09:41 ICT · eligible offer fixture</small></div><div class="evidence-item"><b>Purchasing rules · procurement-demo / v1</b>Approved supplier, positive quantity, matching unit and currency, delivery and budget checks pass.<br><small>Illustrative checks, not a live validation result</small></div></details>`;
const terms = () => `<details class="disclosure" id="terms" ${state.terms ? 'open' : ''}><summary>Exact action & scope<span>Revision 3</span></summary><dl class="terms"><dt>Action</dt><dd>Create one draft purchase order</dd><dt>Tenant / company</dt><dd>northstar-demo / NS-01</dd><dt>Connection / subject</dt><dd>demo-procurement / demo-buyer</dd><dt>Supplier</dt><dd>Northline Paper · SUP-042</dd><dt>Item / quantity / unit</dt><dd>PKG-104 / 240 / unit</dd><dt>Unit price / currency</dt><dd>4.50 / USD</dd><dt>Tax / total</dt><dd>0.00 / 1,080.00</dd><dt>Delivery / warehouse</dt><dd>2026-10-16 / WH-CENTRAL</dd><dt>Source revisions</dt><dd>INV-104:18 / OFF-042:6</dd><dt>Rules / mapping</dt><dd>procurement-demo:1 / demo:1</dd><dt>Expected effect</dt><dd>Create draft only; no confirmation, email, receipt or payment.</dd><dt>Approval binding</dt><dd>Illustrative revision 3. No real digest or authorization is produced by this mockup.</dd></dl></details>`;
const activity = () => `<details class="disclosure"><summary>Recorded activity<span>Fixture events</span></summary><ol class="milestones"><li>Task received<small>09:41 · Requested budget and date retained</small></li><li>Context read<small>09:41 · Inventory and eligible offer fixtures</small></li><li>Proposal prepared<small>09:42 · Revision 3, awaiting explicit approval</small></li></ol></details>`;
const button = (id, text, style='primary') => `<button id="${id}" class="${style}">${text}</button>`;
function render() {
  const s = state.scenario;
  $('#scenario').value = s;
  $('#direction').value = state.preset;
  $('#agent').dataset.preset = state.preset;
  $('#agent').dataset.mode = state.mode;
  $('#expand').setAttribute('aria-label', state.mode === 'expanded' ? 'Restore floating overlay' : 'Expand overlay');
  $('#expand').title = $('#expand').getAttribute('aria-label');
  $('#launcher-status').textContent = statuses[s];
  document.querySelectorAll('[data-preset] button[data-preset]').forEach(b => b.setAttribute('aria-pressed', b.dataset.preset === state.preset));
  document.querySelectorAll('button[data-mode]').forEach(b => b.setAttribute('aria-pressed', b.dataset.mode === state.mode));
  let content = s === 'ready' ? '' : userMessage() + assistantLabel();
  let footer = '';
  if (s === 'ready') {
    content += `<div class="ready-art" aria-hidden="true">✳</div><div class="eyebrow">A LITTLE HELP. A LOT OF POSSIBILITY.</div><h2 class="ready-title">What can I take<br>off your plate?</h2><p class="response-copy">Check stock, compare supplier offers, or prepare a draft order. You review every proposed change.</p><div class="suggestions"><button data-start="draft"><div>Cover the packaging sleeve shortage<small>Prepare a draft within your budget</small></div><span>↗</span></button><button data-start="review"><div>Review the proposed order<small>Inspect quantity, cost and delivery</small></div><span>↗</span></button><button data-start="evidence"><div>Understand the supplier choice<small>Inspect the proposal’s source evidence</small></div><span>↗</span></button></div>`;
    footer = `<form id="composer" class="composer"><textarea id="prompt" aria-label="Task request" placeholder="Tell me the outcome you need…">${escapeHTML(state.draft)}</textarea><div class="composer-bottom"><span>Purchasing context attached · fixed demo scenario</span><button aria-label="Send task" type="submit">↑</button></div></form>`;
  } else if (s === 'review' || s === 'stale') {
    content += `<h2 class="response-title">Ready for your review.</h2><p class="response-copy">I’ve prepared a draft for the missing 240 sleeves. Review the terms below before anything is created.</p>${s === 'stale' ? '<div class="callout warning"><h3>The offer has changed.</h3><p>This proposal can no longer be approved. Refresh the fixture to review a new proposal.</p></div>' : ''}<div class="review-grid"><div>${artifact()}</div><div>${evidence()}${terms()}${activity()}</div></div>`;
    footer = s === 'stale' ? button('refresh','Refresh proposal · demo') : `<div class="approval-row">${button('decline','Decline','secondary')}${button('approve','Review & approve <span>→</span>')}</div><p class="footer-note">Creates a draft only. Nothing is sent to the supplier.</p>`;
  } else if (s === 'working') {
    content += `<h2 class="response-title">Getting the details together.</h2><p class="response-copy">The original request stays in view while the task progresses.</p><ol class="milestones"><li>Request captured<small>Budget $1,200 · needed by 16 October</small></li><li>Stock snapshot received<small>160 available against 400 required · fixture</small></li><li class="pending">Checking supplier terms<small>Waiting for an eligible offer snapshot</small></li></ol><div class="callout"><b>You can keep working.</b><p>Minimize this panel and return to the same task.</p></div>`;
    footer = `<div class="approval-row">${button('stop','Stop task','secondary')}${button('advance','Preview prepared proposal →')}</div><p class="footer-note">Manual scene transition · no background execution</p>`;
  } else if (s === 'clarify') {
    content += `<h2 class="response-title">One detail before I start.</h2><p class="response-copy">Which warehouse needs the 240 sleeves? Your $1,200 budget and 16 October deadline are retained.</p><div class="clarification"><button id="central">Central warehouse <span>Use this location →</span></button></div><p class="footer-note">Only the Central warehouse fixture is included.</p>`;
    footer = button('stop','Stop task','secondary');
  } else if (s === 'executing' || s === 'verifying') {
    content += `<h2 class="response-title">${s === 'executing' ? 'Your approval is recorded.' : 'Draft created. Checking the details.'}</h2><p class="response-copy">${s === 'executing' ? 'The approved draft is being submitted. Approval alone does not mean the order exists.' : 'A creation receipt is available. A separate read-back still needs to confirm the result.'}</p><ol class="milestones"><li>Revision 3 explicitly approved<small>Jamie Lee · scoped to one draft · fixture</small></li><li class="${s === 'executing' ? 'pending' : ''}">${s === 'executing' ? 'Submitting draft order' : 'Creation receipt recorded'}<small>${s === 'executing' ? 'No committed result yet' : 'PO-DEMO-0084 · committed fixture effect'}</small></li>${s === 'verifying' ? '<li class="pending">Independent read-back pending<small>Checking supplier, quantity, amount and draft state</small></li>' : ''}</ol>`;
    footer = button('advance', s === 'executing' ? 'Preview committed / verifying →' : 'Preview verified result →') + '<p class="footer-note">Manual scene transition · synthetic result</p>';
  } else if (s === 'uncertain') {
    content += `<h2 class="response-title">We don’t have a confirmed outcome.</h2><p class="response-copy">The request was sent, but the connection ended before a receipt arrived. A draft may already exist.</p><div class="callout warning"><h3>Creation status is unknown</h3><p>Repeating the write could create another order. Check the existing request’s status before taking further action.</p></div><div class="artifact"><div class="artifact-body"><div class="line-item"><b>Packaging sleeves · 240 units</b><strong>$1,080.00</strong><small>Northline Paper</small><small>Outcome unknown</small></div></div></div>${state.reconciled ? '<div class="callout"><h3>Status still unresolved</h3><p>The simulated read found no authoritative receipt. Leave the request unresolved for an operator; no write was replayed.</p></div>' : ''}${terms()}`;
    footer = button('reconcile','Check existing request status') + '<p class="footer-note">Read-only simulation · does not repeat the order</p>';
  } else if (s === 'verified') {
    content += `<h2 class="response-title">One less thing on your list.</h2><p class="response-copy">The draft was created and its saved details match the approved proposal in this simulated read-back.</p><div class="callout success"><div class="eyebrow">INDEPENDENTLY VERIFIED · FIXTURE</div><strong class="result-id">PO-DEMO-0084 <span>↗</span></strong><p>Northline Paper · 240 packaging sleeves</p><div class="result-fields"><b>$1,080.00 USD</b><span>Due 16 Oct · Draft</span></div></div><ol class="milestones"><li>Creation receipt recorded<small>One draft · PO-DEMO-0084</small></li><li>Separate read-back matched<small>Supplier, item, quantity, price, date and draft state</small></li></ol><p class="response-copy">The order is still a draft. Nothing has been sent, confirmed or paid.</p><details class="disclosure" id="saved-draft"><summary>Saved draft fields<span>PO-DEMO-0084</span></summary>${artifact(true)}${terms()}</details>${evidence()}`;
    footer = `<div class="approval-row">${button('new-task','New task','secondary')}${button('inspect','Inspect saved draft ↗')}</div>`;
  } else {
    content += `<h2 class="response-title">${s === 'rejected' ? 'Draft declined.' : 'Task stopped.'}</h2><p class="response-copy">${s === 'rejected' ? 'Your decision is recorded in this simulation. The proposed order was not submitted.' : 'Stopped before any write was submitted in this scene.'} You can start a new request when you’re ready.</p>`;
    footer = button('new-task','Start a new task →');
  }
  $('#stream').innerHTML = content;
  $('#agent-footer').innerHTML = footer;
  $('#announcement').textContent = statuses[s];
  $('#prompt')?.addEventListener('input', e => { state.draft = e.target.value; });
  $('#composer')?.addEventListener('submit', e => { e.preventDefault(); if (!state.draft.trim()) return; intent = state.draft.trim(); scene('clarify'); });
  $('#evidence')?.addEventListener('toggle', e => { state.evidence = e.target.open; });
  $('#terms')?.addEventListener('toggle', e => { state.terms = e.target.open; });
}
function scene(next) { state.scenario = next; render(); $('#stream').scrollTop = 0; }
function changeView() {
  if ($('#confirmation').open) $('#confirmation').close();
  render();
}
$('#scenario').addEventListener('change', e => { state.reconciled = false; scene(e.target.value); });
$('#direction').addEventListener('change', e => { state.preset = e.target.value; changeView(); });
$('#appearance').addEventListener('click', () => { const open = $('#preferences').hidden; $('#preferences').hidden = !open; $('#appearance').setAttribute('aria-expanded', open); });
$('#expand').addEventListener('click', () => { state.mode = state.mode === 'expanded' ? 'floating' : 'expanded'; changeView(); });
function minimize() { $('#agent').hidden = true; $('#launcher').hidden = false; $('#launcher').focus(); }
$('#minimize').addEventListener('click', minimize);
$('#launcher').addEventListener('click', () => { $('#agent').hidden = false; $('#launcher').hidden = true; $('#appearance').focus(); });
$('#restart').addEventListener('click', () => { Object.assign(state,{scenario:'review',preset:'calm',mode:'floating',draft:'',evidence:false,terms:false,reconciled:false}); intent=defaultIntent; $('#agent').hidden=false; $('#launcher').hidden=true; $('#preferences').hidden=true; $('#appearance').setAttribute('aria-expanded','false'); render(); });
document.addEventListener('click', e => {
  const target = e.target.closest('button');
  if (!target) return;
  if (target.dataset.preset) { state.preset=target.dataset.preset; changeView(); }
  if (target.dataset.mode) { state.mode=target.dataset.mode; changeView(); }
  if (target.dataset.start) { intent=defaultIntent; state.evidence=target.dataset.start==='evidence'; scene(target.dataset.start==='draft'?'working':'review'); if(state.evidence) $('#evidence').scrollIntoView({block:'center'}); }
  const id = target.id;
  if (id === 'approve') { $('#confirmation').showModal(); $('#confirm-title').focus(); }
  if (id === 'back') { $('#confirmation').close(); $('#approve').focus(); }
  if (id === 'confirm') { $('#confirmation').close(); scene('executing'); $('#advance').focus(); }
  if (id === 'decline') scene('rejected');
  if (id === 'stop') scene('cancelled');
  if (id === 'central' || id === 'refresh') scene('review');
  if (id === 'advance') scene(({working:'review', executing:'verifying', verifying:'verified'})[state.scenario]);
  if (id === 'new-task') { state.draft=''; scene('ready'); $('#prompt').focus(); }
  if (id === 'reconcile') { state.reconciled=true; render(); $('#reconcile').focus(); }
  if (id === 'inspect') { $('#saved-draft').open=true; $('#saved-draft').scrollIntoView({block:'start'}); $('#saved-draft summary').focus(); }
});
$('#confirmation').addEventListener('cancel', () => { setTimeout(() => $('#approve')?.focus(),0); });
document.addEventListener('keydown', e => { if(e.key==='Escape' && !$('#confirmation').open && e.target.closest('#agent')) { if(!$('#preferences').hidden) { $('#preferences').hidden=true; $('#appearance').setAttribute('aria-expanded','false'); $('#appearance').focus(); } else minimize(); } });
render();
