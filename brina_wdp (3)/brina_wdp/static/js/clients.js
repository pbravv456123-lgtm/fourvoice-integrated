// Clients page (cards + CRUD + invoice history)
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  clients: [],
  invoicesByClient: new Map(), // cache
  search: "",
  editing: null,
  deleting: null,
  updatePendingPayload: null,
  historyClient: null,
  historyInvoices: [],
  historySearch: "",
};

function toast(msg){
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._tm);
  toast._tm = setTimeout(()=>{ t.hidden = true; }, 2200);
}

function fmtMoney(n){
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function openModal(backdropId, modalId){
  const b = $(backdropId);
  const m = $(modalId);
  b.hidden = false;
  m.hidden = false;
  m.setAttribute("aria-modal", "true");
}
function closeModal(backdropId, modalId){
  const b = $(backdropId);
  const m = $(modalId);
  b.hidden = true;
  m.hidden = true;
  m.setAttribute("aria-modal", "false");
}

async function apiGet(url){
  const res = await fetch(url, { headers: { "Accept":"application/json" } });
  if(!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiJson(url, method, body){
  const res = await fetch(url, {
    method,
    headers: { "Content-Type":"application/json", "Accept":"application/json" },
    body: JSON.stringify(body || {})
  });
  const data = await res.json().catch(()=> ({}));
  if(!res.ok) {
    const e = new Error("Request failed");
    e.data = data;
    throw e;
  }
  return data;
}

function clearFormErrors(){
  $$(".err[data-err]").forEach(el => el.textContent = "");
}
function setFormErrors(errors){
  clearFormErrors();
  Object.entries(errors || {}).forEach(([k,v])=>{
    const el = document.querySelector(`.err[data-err="${k}"]`);
    if(el) el.textContent = v;
  });
}

function clientInitials(name){
  const s = (name || "").trim();
  if(!s) return "??";
  const parts = s.split(/\s+/).slice(0,2);
  return parts.map(p => p[0]?.toUpperCase() || "").join("");
}

function render(){
  const grid = $("#clientsGrid");
  grid.innerHTML = "";
  const q = state.search.toLowerCase().trim();

  // update counters (top subtitle in base + local subtitle)
  const total = state.clients.length;
  const c1 = $("#clientsCount");
  const c2 = $("#clientsCount2");
  if(c1) c1.textContent = String(total);
  if(c2) c2.textContent = String(total);

  const filtered = state.clients.filter(c => {
    if(!q) return true;
    return (c.name || "").toLowerCase().includes(q)
        || (c.email || "").toLowerCase().includes(q)
        || (c.phone || "").toLowerCase().includes(q);
  });

  if(filtered.length === 0){
    // Match example UI: centered empty-state message (not a card)
    // If there are zero clients overall and no search term -> friendly onboarding copy.
    // If user searched but nothing matched -> "No clients found.".
    const msg = (state.clients.length === 0 && !q)
      ? "No clients yet. Add your first client!"
      : "No clients found.";
    grid.innerHTML = `<div class="clients-empty-state">${msg}</div>`;
    return;
  }

  filtered.forEach(c => {
    const card = document.createElement("div");
    card.className = "client-card";
    card.addEventListener("click", ()=> openHistory(c));

    card.innerHTML = `
      <div class="client-head">
        <div class="client-id">
          <div class="client-avatar">${escapeHtml(clientInitials(c.name))}</div>
          <div>
            <div class="client-name">${escapeHtml(c.name)}</div>
          </div>
        </div>

        <div class="client-actions" aria-label="Client actions">
          <button class="icon-action" data-act="edit" type="button" aria-label="Edit client">
            ${svgPencil()}
          </button>
          <button class="icon-action" data-act="del" type="button" aria-label="Delete client">
            ${svgTrash()}
          </button>
        </div>
      </div>

      <div class="client-lines">
        <div class="client-line">${svgMail()}<span>${escapeHtml(c.email)}</span></div>
        <div class="client-line">${svgPhone()}<span>${escapeHtml(c.phone)}</span></div>
        <div class="client-line">${svgPin()}<span>${escapeHtml(shorten(c.address, 44))}</span></div>
      </div>

      <div class="client-divider"></div>

      <div class="client-metrics">
        <div class="metric">
          <div class="metric-label muted">Linked Invoices</div>
          <div class="metric-value" data-stat="count">—</div>
        </div>
        <div class="metric right">
          <div class="metric-label muted">Total Billed</div>
          <div class="metric-value primary" data-stat="total">S$—</div>
        </div>
      </div>

      <div class="client-foot muted small">Based on invoices referencing this saved client</div>
    `;

    card.querySelector('[data-act="edit"]').addEventListener("click", (e)=>{
      e.stopPropagation();
      openEdit(c);
    });
    card.querySelector('[data-act="del"]').addEventListener("click", (e)=>{
      e.stopPropagation();
      openDelete(c);
    });

    grid.appendChild(card);

    // stats (async)
    loadStatsForCard(c, card).catch(()=>{});
  });
}

function svgPencil(){
  return `
  <svg viewBox="0 0 24 24" width="18" height="18" class="ic" aria-hidden="true">
    <path d="M12 20h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
  </svg>`;
}

function svgTrash(){
  return `
  <svg viewBox="0 0 24 24" width="18" height="18" class="ic" aria-hidden="true">
    <path d="M3 6h18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    <path d="M8 6V4h8v2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    <path d="M19 6l-1 14H6L5 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
    <path d="M10 11v6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    <path d="M14 11v6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  </svg>`;
}

function svgMail(){
  return `
  <svg viewBox="0 0 24 24" width="18" height="18" class="ic" aria-hidden="true">
    <path d="M4 4h16v16H4z" fill="none" stroke="currentColor" stroke-width="2" opacity="0"/>
    <path d="M4 6h16v12H4z" fill="none" stroke="currentColor" stroke-width="2"/>
    <path d="M4 7l8 6 8-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
  </svg>`;
}

function svgPhone(){
  return `
  <svg viewBox="0 0 24 24" width="18" height="18" class="ic" aria-hidden="true">
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.08 4.18 2 2 0 0 1 4.06 2h3a2 2 0 0 1 2 1.72c.12.86.31 1.7.57 2.5a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.58-1.09a2 2 0 0 1 2.11-.45c.8.26 1.64.45 2.5.57A2 2 0 0 1 22 16.92z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
  </svg>`;
}

function svgPin(){
  return `
  <svg viewBox="0 0 24 24" width="18" height="18" class="ic" aria-hidden="true">
    <path d="M21 10c0 6-9 13-9 13S3 16 3 10a9 9 0 0 1 18 0z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
    <circle cx="12" cy="10" r="3" fill="none" stroke="currentColor" stroke-width="2"/>
  </svg>`;
}

function escapeHtml(str){
  return (str ?? "").toString()
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}
function shorten(s, n){
  const t = (s || "").trim();
  if(t.length <= n) return t;
  return t.slice(0, n-1) + "…";
}

async function loadStatsForCard(client, cardEl){
  const data = await apiGet(`/api/invoices?client_id=${encodeURIComponent(client.id)}&bill_to_name=${encodeURIComponent(client.name)}`);
  const invoices = data.invoices || [];
  const total = invoices.reduce((sum, inv)=> sum + Number(inv.total_amount || 0), 0);
  const countEl = cardEl.querySelector('[data-stat="count"]');
  const totalEl = cardEl.querySelector('[data-stat="total"]');
  if(countEl) countEl.textContent = String(invoices.length);
  if(totalEl) totalEl.textContent = `S$${fmtMoney(total)}`;
}

async function refresh(){
  const data = await apiGet("/api/clients");
  state.clients = data.clients || [];
  render();
}

function openAdd(){
  state.editing = null;
  $("#clientModalTitle").textContent = "Add New Client";
  const sub = $("#clientModalSub");
  if(sub) sub.textContent = "Enter complete client details";
  $("#clientModalSave").textContent = "Add Client";
  $("#c_name").value = "";
  $("#c_email").value = "";
  $("#c_phone").value = "";
  $("#c_address").value = "";
  clearFormErrors();
  openModal("#clientModalBackdrop", "#clientModal");
}

function openEdit(client){
  state.editing = client;
  $("#clientModalTitle").textContent = "Edit Client";
  const sub = $("#clientModalSub");
  if(sub) sub.textContent = "Update client information";
  $("#clientModalSave").textContent = "Update Client";
  $("#c_name").value = client.name || "";
  $("#c_email").value = client.email || "";
  $("#c_phone").value = client.phone || "";
  $("#c_address").value = client.address || "";
  clearFormErrors();
  openModal("#clientModalBackdrop", "#clientModal");
}

function openDelete(client){
  state.deleting = client;
  $("#deleteText").textContent = `Are you sure you want to delete "${client.name}"? This action cannot be undone and will affect all related invoices.`;
  openModal("#deleteBackdrop", "#deleteModal");
}

function openUpdateConfirm(){
  $("#confirmText").textContent = `Are you sure you want to update this client’s information? This will apply to all future invoices.`;

  // Dim the underlying Add/Edit modal while the confirmation is open
  const baseModal = $("#clientModal");
  if(baseModal && !baseModal.hidden){
    baseModal.classList.add("is-dimmed");
  }

  openModal("#confirmBackdrop", "#confirmModal");
}

async function submitClientForm(e){
  e.preventDefault();
  const payload = {
    name: $("#c_name").value.trim(),
    email: $("#c_email").value.trim(),
    phone: $("#c_phone").value.trim(),
    address: $("#c_address").value.trim(),
  };

  // editing path shows confirm
  if(state.editing){
    state.updatePendingPayload = payload;
    openUpdateConfirm();
    return;
  }

  try{
    const out = await apiJson("/api/clients", "POST", payload);
    closeModal("#clientModalBackdrop", "#clientModal");
    toast("Client added");
    await refresh();
  }catch(err){
    setFormErrors(err.data?.errors || {});
  }
}

async function confirmUpdate(){
  try{
    const out = await apiJson(`/api/clients/${state.editing.id}`, "PUT", state.updatePendingPayload);
    closeConfirm();
    closeModal("#clientModalBackdrop", "#clientModal");
    toast("Client updated");
    state.editing = null;
    state.updatePendingPayload = null;
    await refresh();
  }catch(err){
    closeConfirm();
    setFormErrors(err.data?.errors || {});
  }
}

async function confirmDelete(){
  if(!state.deleting) return;
  try{
    await apiJson(`/api/clients/${state.deleting.id}`, "DELETE", {});
    closeModal("#deleteBackdrop", "#deleteModal");
    toast("Client deleted");
    state.deleting = null;
    await refresh();
  }catch(_err){
    closeModal("#deleteBackdrop", "#deleteModal");
    toast("Delete failed");
  }
}

// -------- Invoice history modal --------
async function openHistory(client){
  state.historyClient = client;
  $("#invTitle").textContent = "Invoice history";
  $("#invSub").textContent = `${client.name} • ${client.email}`;
  $("#invSearch").value = "";
  state.historySearch = "";

  const data = await apiGet(`/api/invoices?client_id=${encodeURIComponent(client.id)}&bill_to_name=${encodeURIComponent(client.name)}`);
  state.historyInvoices = data.invoices || [];
  renderHistory();
  openModal("#invBackdrop", "#invModal");
}

function renderHistory(){
  const invs = state.historyInvoices.slice();
  const q = state.historySearch.toLowerCase().trim();
  const filtered = invs.filter(inv => !q || (inv.invoice_number || "").toLowerCase().includes(q));

  const total = filtered.reduce((sum, inv)=> sum + Number(inv.total_amount || 0), 0);
  const paid = filtered.filter(inv => (inv.status || "").toLowerCase() === "paid").length;
  const outstanding = filtered.filter(inv => ["sent","approved","overdue","pending_approval"].includes((inv.status||"").toLowerCase())).length;

  $("#invStats").innerHTML = `
    <div class="kpi"><span class="muted">Invoices</span><span class="v mono">${filtered.length}</span></div>
    <div class="kpi"><span class="muted">Billed</span><span class="v mono">S$${fmtMoney(total)}</span></div>
    <div class="kpi"><span class="muted">Outstanding</span><span class="v mono">${outstanding}</span></div>
  `;

  const tbody = $("#invTbody");
  tbody.innerHTML = "";
  if(filtered.length === 0){
    tbody.innerHTML = `<tr><td colspan="4" class="muted">No invoices found.</td></tr>`;
    return;
  }

  filtered.forEach(inv=>{
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">${escapeHtml(inv.invoice_number)}</td>
      <td>${escapeHtml(inv.issue_date)}</td>
      <td class="right mono">S$${fmtMoney(inv.total_amount)}</td>
      <td><span class="badge">${escapeHtml((inv.status || "draft").toUpperCase())}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// -------- wire up --------
$("#addClientBtn").addEventListener("click", openAdd);
$("#searchInput").addEventListener("input", (e)=>{ state.search = e.target.value; render(); });

$("#clientModalClose").addEventListener("click", ()=> closeModal("#clientModalBackdrop", "#clientModal"));
$("#clientModalCancel").addEventListener("click", ()=> closeModal("#clientModalBackdrop", "#clientModal"));
$("#clientModalBackdrop").addEventListener("click", ()=> closeModal("#clientModalBackdrop", "#clientModal"));
$("#clientForm").addEventListener("submit", submitClientForm);

function closeConfirm(){
  closeModal("#confirmBackdrop", "#confirmModal");
  const baseModal = $("#clientModal");
  if(baseModal){
    baseModal.classList.remove("is-dimmed");
  }
}

$("#confirmClose").addEventListener("click", closeConfirm);
$("#confirmCancel").addEventListener("click", closeConfirm);
$("#confirmBackdrop").addEventListener("click", closeConfirm);
$("#confirmOk").addEventListener("click", confirmUpdate);

$("#deleteClose").addEventListener("click", ()=> closeModal("#deleteBackdrop", "#deleteModal"));
$("#deleteCancel").addEventListener("click", ()=> closeModal("#deleteBackdrop", "#deleteModal"));
$("#deleteBackdrop").addEventListener("click", ()=> closeModal("#deleteBackdrop", "#deleteModal"));
$("#deleteOk").addEventListener("click", confirmDelete);

$("#invClose").addEventListener("click", ()=> closeModal("#invBackdrop", "#invModal"));
$("#invBackdrop").addEventListener("click", ()=> closeModal("#invBackdrop", "#invModal"));
$("#invSearch").addEventListener("input", (e)=>{ state.historySearch = e.target.value; renderHistory(); });

refresh().catch(()=> toast("Failed to load clients"));
