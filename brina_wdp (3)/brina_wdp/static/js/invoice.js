// Create Invoice page (saved/one-off + items + totals)
const $ = (sel) => document.querySelector(sel);

const state = {
  mode: "saved",          // saved | oneoff
  clients: [],
  selectedClient: null,
  items: [],
  activeItemIdForProduct: null,
  products: [],
  prodFilter: "All",
};


// =========================
// UI feedback: active state for key buttons
// =========================
const clientPickerBtn = document.querySelector("#openClientPicker");
const uploadBtnEl = document.querySelector("#uploadBtn");

function setClientPickerActive(on){
  if(!clientPickerBtn) return;
  clientPickerBtn.classList.toggle("is-selected", !!on);
}
function setUploadBtnActive(on){
  if(!uploadBtnEl) return;
  uploadBtnEl.classList.toggle("is-selected", !!on);
}

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
function currencySymbol(code){
  switch(code){
    case "SGD": return "S$";
    case "USD": return "$";
    case "EUR": return "€";
    case "GBP": return "£";
    case "MYR": return "RM";
    default: return "";
  }
}

async function apiGet(url){
  const res = await fetch(url, { headers: { "Accept":"application/json" } });
  if(!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiPost(url, body){
  const res = await fetch(url, {
    method:"POST",
    headers: { "Content-Type":"application/json", "Accept":"application/json" },
    body: JSON.stringify(body || {})
  });
  const data = await res.json().catch(()=> ({}));
  if(!res.ok){
    const e = new Error("Request failed");
    e.data = data;
    throw e;
  }
  return data;
}

function openModal(backdropId, modalId){
  $(backdropId).hidden = false;
  $(modalId).hidden = false;
  $(modalId).setAttribute("aria-modal","true");
}
function closeModal(backdropId, modalId){
  $(backdropId).hidden = true;
  $(modalId).hidden = true;
  $(modalId).setAttribute("aria-modal","false");
}

// -------------------------
// Product picker
// -------------------------
function openProductPicker(itemId){
  state.activeItemIdForProduct = itemId;
  const s = $("#prodSearch");
  if(s) s.value = "";

  // restore active pill
  const current = state.prodFilter || "All";
  document.querySelectorAll(".ci-pill").forEach(p=>{
    p.classList.toggle("active", (p.dataset.cat || "All") === current);
  });
  renderProductList();
  openModal("#prodBackdrop", "#prodModal");
  setTimeout(()=> s?.focus(), 0);
}

function closeProductPicker(){
  closeModal("#prodBackdrop", "#prodModal");
  state.activeItemIdForProduct = null;
}

function setMode(mode){
  state.mode = mode;
  const err = document.querySelector("#clientErr");
  if(err) err.textContent = "";
}

function renderSelectedClientUI(){
  const emptyBtn = $("#openClientPicker");
  const picked = $("#ciClientPicked");
  const txt = $("#ciClientSelectText");

  if(!picked || !emptyBtn) return;

  const oneoffName = ($("#oneoffName")?.value || "").trim();

  // none selected
  if(state.mode === "saved" && !state.selectedClient && !oneoffName){
    picked.hidden = true;
    picked.innerHTML = "";
    emptyBtn.hidden = false;
    if(txt) txt.textContent = "Click to select client";
    return;
  }

  // show picked pill
  emptyBtn.hidden = true;
  picked.hidden = false;

  if(state.mode === "oneoff"){
    picked.innerHTML = `
      <div class="ci-client-pill oneoff">
        <div class="left">
          <div class="ci-client-kicker">One-off Client</div>
          <div class="ci-client-name">${escapeHtml(oneoffName)}</div>
        </div>
        <div class="ci-client-actions">
          <button type="button" class="ci-client-link edit" id="ciOneoffEdit">Edit</button>
          <button type="button" class="ci-client-link remove" id="ciClientRemove">Remove</button>
        </div>
      </div>
    `;
    $("#ciOneoffEdit")?.addEventListener("click", ()=> openOneoffModal(true));
    $("#ciClientRemove")?.addEventListener("click", clearSelectedClient);
  } else {
    const c = state.selectedClient;
    picked.innerHTML = `
      <div class="ci-client-pill">
        <div class="left">
          <div class="ci-client-kicker">Saved Client</div>
          <div class="ci-client-name">${escapeHtml(c?.name || "")}</div>
        </div>
        <div class="ci-client-actions">
          <button type="button" class="ci-client-link change" id="ciClientChange">Change</button>
          <button type="button" class="ci-client-link remove" id="ciClientRemove">Remove</button>
        </div>
      </div>
    `;
    $("#ciClientChange")?.addEventListener("click", openPicker);
    $("#ciClientRemove")?.addEventListener("click", clearSelectedClient);
  }

  // legacy badge (kept for compatibility, stays hidden)
  const badge = document.querySelector("#selectedClientBadge");
  if(badge){
    badge.hidden = true;
    badge.innerHTML = "";
  }
}

function clearSelectedClient(){
  state.selectedClient = null;
  $("#oneoffName").value = "";
  setMode("saved");
  renderSelectedClientUI();
  $("#clientErr").textContent = "";
}

function setSelectedClient(client){
  state.selectedClient = client;
  $("#oneoffName").value = "";
  setMode("saved");
  renderSelectedClientUI();
}

function setOneoffClient(name){
  state.selectedClient = null;
  $("#oneoffName").value = (name || "").trim();
  setMode("oneoff");
  renderSelectedClientUI();
}

function escapeHtml(str){
  return (str ?? "").toString()
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}

function todayISO(){
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth()+1).padStart(2,"0");
  const dd = String(d.getDate()).padStart(2,"0");
  return `${yyyy}-${mm}-${dd}`;
}
function addDaysISO(baseISO, days){
  const d = new Date(baseISO);
  d.setDate(d.getDate() + Number(days || 0));
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth()+1).padStart(2,"0");
  const dd = String(d.getDate()).padStart(2,"0");
  return `${yyyy}-${mm}-${dd}`;
}

async function loadNextNumber(){
  const data = await apiGet("/api/invoices/next-number");
  $("#invoiceNumber").value = data.invoice_number || "";
}

async function loadClients(){
  const data = await apiGet("/api/clients");
  state.clients = data.clients || [];
}

function openPicker(){
  $("#pickerSearch").value = "";
  renderPicker("");
  setClientPickerActive(true);
  openModal("#pickerBackdrop", "#pickerModal");
}

function closePicker(){
  setClientPickerActive(false);
  closeModal("#pickerBackdrop", "#pickerModal");
}
function renderPicker(q){
  const grid = $("#pickerGrid");
  const search = (q || "").toLowerCase().trim();
  const list = state.clients.filter(c => !search
    || (c.name||"").toLowerCase().includes(search)
    || (c.email||"").toLowerCase().includes(search)
    || (c.phone||"").toLowerCase().includes(search)
  );

  grid.innerHTML = "";
  $("#savedTitle").textContent = `Saved Clients (${state.clients.length})`;

  if(list.length === 0){
    grid.innerHTML = `<div class="muted" style="padding:10px 4px;">No matching clients.</div>`;
    return;
  }

  list.forEach(c=>{
    const el = document.createElement("div");
    el.className = "ci-saved-card";
    el.innerHTML = `
      <div class="ci-saved-ic" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="18" height="18" class="ic">
          <path d="M4 21V3h10l6 6v12H4Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M14 3v6h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        </svg>
      </div>
      <div style="min-width:0;">
        <div class="ci-saved-name">${escapeHtml(c.name)}</div>
        <div class="ci-saved-meta">
          <div class="row">
            <svg viewBox="0 0 24 24" width="16" height="16" class="ic" aria-hidden="true">
              <path d="M4 4h16v16H4V4Z" fill="none" stroke="currentColor" stroke-width="2"/>
              <path d="M4 7l8 6 8-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <span>${escapeHtml(c.email)}</span>
          </div>
          <div class="row">
            <svg viewBox="0 0 24 24" width="16" height="16" class="ic" aria-hidden="true">
              <path d="M22 16.9v3a2 2 0 0 1-2.2 2A19.8 19.8 0 0 1 3 5.2 2 2 0 0 1 5 3h3a2 2 0 0 1 2 1.7l.5 2.6a2 2 0 0 1-.6 1.9l-1.2 1.2a16 16 0 0 0 6.1 6.1l1.2-1.2a2 2 0 0 1 1.9-.6l2.6.5A2 2 0 0 1 22 16.9Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>${escapeHtml(c.phone)}</span>
          </div>
          <div class="row">
            <svg viewBox="0 0 24 24" width="16" height="16" class="ic" aria-hidden="true">
              <path d="M12 21s7-4.5 7-11a7 7 0 1 0-14 0c0 6.5 7 11 7 11Z" fill="none" stroke="currentColor" stroke-width="2"/>
              <circle cx="12" cy="10" r="2.5" fill="none" stroke="currentColor" stroke-width="2"/>
            </svg>
            <span>${escapeHtml(shorten(c.address, 46))}</span>
          </div>
        </div>
      </div>
    `;
    el.addEventListener("click", ()=>{
      setSelectedClient(c);
      closePicker();
      $("#clientErr").textContent = "";
    });
    grid.appendChild(el);
  });
}
function clientInitials(name){
  const s = (name || "").trim();
  if(!s) return "??";
  const parts = s.split(/\s+/).slice(0,2);
  return parts.map(p => p[0]?.toUpperCase() || "").join("");
}
function shorten(s, n){
  const t = (s || "").trim();
  if(t.length <= n) return t;
  return t.slice(0, n-1) + "…";
}

// Items
function addItemRow(item = { description:"", quantity:1, unit_price:0 }){
  const id = crypto.randomUUID();
  const row = { id, ...item };
  state.items.push(row);
  renderItems();
  return id;
}

function removeItem(id){
  state.items = state.items.filter(x => x.id !== id);
  renderItems();
}

function updateItem(id, key, val){
  const it = state.items.find(x => x.id === id);
  if(!it) return;
  if(key === "quantity"){ it[key] = Math.max(1, parseInt(val || 1)); renderTotals(); return; }
  if(key === "unit_price"){
    it[key] = Number(val || 0);
  } else {
    it[key] = val;
  }
  renderTotals();
}

function renderItems(){
  const wrap = $("#itemsWrap");
  wrap.innerHTML = "";
  if(state.items.length === 0){
    wrap.innerHTML = `<div class="item-row"><button type="button" class="ci-prod-btn">Select product</button><input class="input" type="number" value="1" disabled><input class="input" type="number" value="0" disabled><div class="mono right">S$0.00</div></div>`;
  } else {
    state.items.forEach(it=>{
      const el = document.createElement("div");
      el.className = "item-row";
      const lineTotal = (Number(it.quantity||0) * Number(it.unit_price||0));
      const label = (it.description || "").trim() ? escapeHtml(it.description) : "Select product";
      el.innerHTML = `
        <button type="button" class="ci-prod-btn" data-action="pick-product" data-id="${it.id}">${label}</button>
        <input class="input" type="number" min="1" step="1" value="${it.quantity}" data-k="quantity">
        <input class="input" type="number" min="0" step="0.01" value="${it.unit_price}" data-k="unit_price">
        <div class="mono right">${currencySymbol($("#currency").value)}${fmtMoney(lineTotal)}</div><button type="button" class="ci-del-btn" data-del="${it.id}">✕</button>
      `;
      el.querySelector("button[data-action='pick-product']")
        .addEventListener("click", ()=> openProductPicker(it.id));

      const inputs = el.querySelectorAll("input");
      inputs.forEach(inp=>{
        inp.addEventListener("input", (e)=>{
          updateItem(it.id, inp.dataset.k, e.target.value);
        });
      });
      wrap.appendChild(el);
      const delBtn = el.querySelector(".ci-del-btn");
      if(delBtn){
        delBtn.addEventListener("click", ()=> removeItem(it.id));
      }
    });
  }
  renderTotals();
}

function totals(){
  const subtotal = state.items.reduce((sum, it)=>{
    const lt = Number(it.quantity||0) * Number(it.unit_price||0);
    return sum + (isFinite(lt) ? lt : 0);
  }, 0);
  const gstRate = Number($("#gstRate").value || 0);
  const gst = subtotal * (gstRate / 100.0);
  const total = subtotal + gst;
  return { subtotal, gst, total, gstRate };
}

function renderTotals(){
  const cur = $("#currency").value;
  const sym = currencySymbol(cur);
  const t = totals();
  $("#subtotalText").textContent = `${sym}${fmtMoney(t.subtotal)}`;
  $("#gstText").textContent = `${sym}${fmtMoney(t.gst)}`;
  $("#totalText").textContent = `${sym}${fmtMoney(t.total)}`;
}

// -------------------------
// Products (reads from API; falls back to a stub)
// -------------------------
async function loadProducts(){
  try{
    const out = await apiGet("/api/catalogue-items");
    state.products = out.items || [];
    return;
  }catch(_e){
    // fallback stub
  }
  state.products = [
    { id: 1, name: "apple", sku: "PRD-002", category: "Products", unit_price: 200.0, description: "" }
  ];
}

function renderProductList(){
  const list = $("#prodList");
  if(!list) return;

  const q = ($("#prodSearch")?.value || "").trim().toLowerCase();
  const cat = state.prodFilter || "All";

  let items = [...(state.products || [])];
  if(cat !== "All") items = items.filter(x => (x.category||"") === cat);
  if(q){
    items = items.filter(x =>
      (x.name||"").toLowerCase().includes(q)
      || (x.sku||"").toLowerCase().includes(q)
      || (x.description||"").toLowerCase().includes(q)
    );
  }

  const title = $("#prodListTitle");
  if(title) title.textContent = `Select from Catalogue (${items.length})`;

  if(items.length === 0){
    list.innerHTML = `<div class="muted" style="padding:10px 2px;">No matching items.</div>`;
    return;
  }

  list.innerHTML = "";
  items.forEach(it=>{
    const card = document.createElement("div");
    card.className = "ci-prod-card";
    card.innerHTML = `
      <div class="ci-prod-ic" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="22" height="22" class="ic">
          <path d="M12 2 3 7v10l9 5 9-5V7l-9-5Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M12 22V12" fill="none" stroke="currentColor" stroke-width="2"/>
          <path d="M21 7l-9 5-9-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        </svg>
      </div>
      <div>
        <div class="ci-prod-name">${escapeHtml(it.name)}</div>
        <div class="ci-prod-meta">
          <span class="ci-tag">
            <svg viewBox="0 0 24 24" width="14" height="14" class="ic" aria-hidden="true">
              <path d="M20 13l-7 7-11-11V2h7l11 11Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
              <circle cx="7.5" cy="7.5" r="1.5" fill="currentColor"/>
            </svg>
            ${escapeHtml(it.sku || "")}
          </span>
          <span class="ci-tag cat">${escapeHtml(it.category || "")}</span>
        </div>
      </div>
      <div class="ci-prod-price">S$${fmtMoney(Number(it.unit_price||0))}</div>
    `;

    card.addEventListener("click", ()=>{
      const row = state.items.find(x => x.id === state.activeItemIdForProduct);
      if(!row) return;
      row.description = it.name;
      row.unit_price = Number(it.unit_price || 0);
      renderItems();
      closeProductPicker();
    });
    list.appendChild(card);
  });
}

function clearErrors(){
  $("#clientErr").textContent = "";
  $("#invoiceNumberErr").textContent = "";
  $("#issueDateErr").textContent = "";
  $("#dueDateErr").textContent = "";
  $("#itemsErr").textContent = "";
}

function validate(){
  clearErrors();
  let ok = true;

  if(state.mode === "saved"){
    if(!state.selectedClient){
      $("#clientErr").textContent = "Please select a client.";
      ok = false;
    }
  } else {
    const n = ($("#oneoffName").value || "").trim();
    if(!n){
      $("#clientErr").textContent = "Please enter a one-off client name.";
      ok = false;
    }
  }

  if(!($("#invoiceNumber").value || "").trim()){
    $("#invoiceNumberErr").textContent = "Invoice number is required.";
    ok = false;
  }
  if(!($("#issueDate").value || "").trim()){
    $("#issueDateErr").textContent = "Issue date is required.";
    ok = false;
  }
  if(!($("#dueDate").value || "").trim()){
    $("#dueDateErr").textContent = "Due date is required.";
    ok = false;
  }

  const hasItem = state.items.some(it => (it.description || "").trim());
  if(!hasItem){
    $("#itemsErr").textContent = "Add at least one item with a description.";
    ok = false;
  }

  return ok;
}


async function previewInvoice(){
  $("#saveMsg").textContent = "";
  if(!validate()) return;

  const payload = {
    client_mode: state.mode === "saved" ? "saved" : "oneoff",
    client_id: state.selectedClient?.id || null,
    oneoff_name: ($("#oneoffName").value || "").trim(),
    invoice_number: ($("#invoiceNumber").value || "").trim(),
    currency: $("#currency").value,
    issue_date: $("#issueDate").value,
    due_date: $("#dueDate").value,
    notes: ($("#notes").value || "").trim(),
    gst_rate: Number($("#gstRate").value || 0),
    items: state.items.map(it => ({
      description: (it.description || "").trim(),
      quantity: Number(it.quantity || 0),
      unit_price: Number(it.unit_price || 0),
    })),
  };

  try{
    const out = await apiPost("/api/invoices", payload);
    const id = out.invoice?.id;
    if(id){
      window.location.href = `/invoice-preview/${id}`;
      return;
    }
    toast("Preview failed");
  }catch(err){
    const errors = err.data?.errors || {};
    if(errors.client) $("#clientErr").textContent = errors.client;
    if(errors.invoice_number) $("#invoiceNumberErr").textContent = errors.invoice_number;
    if(errors.issue_date) $("#issueDateErr").textContent = errors.issue_date;
    if(errors.due_date) $("#dueDateErr").textContent = errors.due_date;
    if(errors.items) $("#itemsErr").textContent = errors.items;
    toast("Preview failed");
  }
}

async function saveDraft(){
  $("#saveMsg").textContent = "";
  if(!validate()) return;

  const payload = {
    client_mode: state.mode === "saved" ? "saved" : "oneoff",
    client_id: state.selectedClient?.id || null,
    oneoff_name: ($("#oneoffName").value || "").trim(),
    invoice_number: ($("#invoiceNumber").value || "").trim(),
    currency: $("#currency").value,
    issue_date: $("#issueDate").value,
    due_date: $("#dueDate").value,
    notes: ($("#notes").value || "").trim(),
    gst_rate: Number($("#gstRate").value || 0),
    items: state.items.map(it => ({
      description: (it.description || "").trim(),
      quantity: Number(it.quantity || 0),
      unit_price: Number(it.unit_price || 0),
    })),
  };

  try{
    const out = await apiPost("/api/invoices", payload);
    toast("Invoice saved (draft)");
    $("#saveMsg").textContent = `Saved ${out.invoice.invoice_number} as draft.`;
    // reset items, regen number
    state.items = [];
    renderItems();
    await loadNextNumber();
  }catch(err){
    const errors = err.data?.errors || {};
    if(errors.client) $("#clientErr").textContent = errors.client;
    if(errors.invoice_number) $("#invoiceNumberErr").textContent = errors.invoice_number;
    if(errors.issue_date) $("#issueDateErr").textContent = errors.issue_date;
    if(errors.due_date) $("#dueDateErr").textContent = errors.due_date;
    if(errors.items) $("#itemsErr").textContent = errors.items;
    toast("Save failed");
  }
}

// Wire up
$("#openClientPicker").addEventListener("click", openPicker);
$("#pickerClose").addEventListener("click", ()=> closePicker());
$("#pickerCancelBtn").addEventListener("click", ()=> closePicker());
$("#pickerBackdrop").addEventListener("click", ()=> closePicker());
$("#pickerSearch").addEventListener("input", (e)=> renderPicker(e.target.value));

$("#oneoffStartBtn").addEventListener("click", ()=> openOneoffModal(false));

// Product picker wiring
const prodClose = document.querySelector("#prodClose");
if(prodClose) prodClose.addEventListener("click", closeProductPicker);
const prodCancel = document.querySelector("#prodCancelBtn");
if(prodCancel) prodCancel.addEventListener("click", closeProductPicker);
const prodBackdrop = document.querySelector("#prodBackdrop");
if(prodBackdrop) prodBackdrop.addEventListener("click", closeProductPicker);
const prodSearch = document.querySelector("#prodSearch");
if(prodSearch) prodSearch.addEventListener("input", ()=> renderProductList());
document.querySelectorAll(".ci-pill").forEach(p=>{
  p.addEventListener("click", ()=>{
    state.prodFilter = p.dataset.cat || "All";
    document.querySelectorAll(".ci-pill").forEach(x=> x.classList.toggle("active", x === p));
    renderProductList();
  });
});

function openOneoffModal(isEdit){
  // close picker if open
  closePicker();
  const current = ( $("#oneoffName").value || "" ).trim();
  if(isEdit && current) $("#oneoffNameInput").value = current;
  else $("#oneoffNameInput").value = "";
  openModal("#oneoffBackdrop", "#oneoffModal");
  setTimeout(()=> $("#oneoffNameInput").focus(), 0);
}

function closeOneoff(){
  closeModal("#oneoffBackdrop", "#oneoffModal");
}

$("#oneoffClose").addEventListener("click", closeOneoff);
$("#oneoffBackdrop").addEventListener("click", closeOneoff);
$("#oneoffBackBtn").addEventListener("click", ()=>{
  closeOneoff();
  openPicker();
});
$("#oneoffContinueBtn").addEventListener("click", ()=>{
  const n = ( $("#oneoffNameInput").value || "" ).trim();
  if(!n){
    toast("Client name is required");
    $("#oneoffNameInput").focus();
    return;
  }
  setOneoffClient(n);
  closeOneoff();
  $("#clientErr").textContent = "";
});


$("#addItemBtn").addEventListener("click", ()=> {
  // If only 1 empty placeholder exists, remove it first
  if(state.items.length === 1){
    const only = state.items[0];
    if(!(only.description || "").trim() && Number(only.quantity) === 1 && Number(only.unit_price) === 0){
      state.items = [];
    }
  }
  addItemRow();
});

$("#currency").addEventListener("change", renderTotals);
$("#gstRate").addEventListener("input", renderTotals);

// invoice number regenerate button removed (keep logic unchanged)

$("#issueDate").addEventListener("change", ()=>{
  // auto-set due date if empty
  if(!$("#dueDate").value){
    $("#dueDate").value = addDaysISO($("#issueDate").value, 30);
  }
});
document.querySelectorAll(".ci-chip").forEach(btn=>{
  btn.addEventListener("click", ()=>{
    const days = btn.dataset.days;
    const issue = $("#issueDate").value || todayISO();
    $("#issueDate").value = issue;
    $("#dueDate").value = addDaysISO(issue, days);
  });
});

$("#saveDraftBtn").addEventListener("click", saveDraft);

const previewBtn = document.querySelector("#previewSubmitBtn");
if(previewBtn){
  previewBtn.addEventListener("click", async ()=>{
    $("#saveMsg").textContent = "";
    if(!validate()) return;

    // Build payload (same as Save Draft)
    const payload = {
      client_mode: state.mode === "saved" ? "saved" : "oneoff",
      client_id: state.selectedClient?.id || null,
      oneoff_name: ($("#oneoffName").value || "").trim(),
      invoice_number: ($("#invoiceNumber").value || "").trim(),
      currency: $("#currency").value,
      issue_date: $("#issueDate").value,
      due_date: $("#dueDate").value,
      notes: ($("#notes").value || "").trim(),
      gst_rate: Number($("#gstRate").value || 0),
      items: state.items.map(it => ({
        description: (it.description || "").trim(),
        quantity: Math.max(1, parseInt(it.quantity || 1)),
        unit_price: Number(it.unit_price || 0),
      })),
    };

    try{
      previewBtn.disabled = true;
      previewBtn.classList.add("is-loading");
      const out = await apiPost("/api/invoices", payload);
      const id = out.invoice?.id;
      if(!id){
        toast("Preview failed");
        previewBtn.disabled = false;
        previewBtn.classList.remove("is-loading");
        return;
      }
      // Go to preview page
      window.location.href = `/invoice-preview/${id}`;
    }catch(err){
      const errors = err.data?.errors || {};
      if(errors.client) $("#clientErr").textContent = errors.client;
      if(errors.invoice_number) $("#invoiceNumberErr").textContent = errors.invoice_number;
      if(errors.issue_date) $("#issueDateErr").textContent = errors.issue_date;
      if(errors.due_date) $("#dueDateErr").textContent = errors.due_date;
      if(errors.items) $("#itemsErr").textContent = errors.items;
      toast("Preview failed");
    }finally{
      previewBtn.disabled = false;
      previewBtn.classList.remove("is-loading");
    }
  });
}
const uploadBtn = document.querySelector("#uploadBtn");

// --- AI Upload PO / Quote ---
const poFileInput = document.querySelector("#poFileInput");
const aiBackdrop = document.querySelector("#aiBackdrop");
const aiModal = document.querySelector("#aiModal");
const aiClose = document.querySelector("#aiClose");
const aiCancelBtn = document.querySelector("#aiCancelBtn");
const aiAddBtn = document.querySelector("#aiAddBtn");
const aiList = document.querySelector("#aiList");
const aiDetectedTitle = document.querySelector("#aiDetectedTitle");
const aiTotalText = document.querySelector("#aiTotalText");
const aiSelectedCount = document.querySelector("#aiSelectedCount");
const aiDocName = document.querySelector("#aiDocName");
const aiDocMeta = document.querySelector("#aiDocMeta");
const aiSelectAllBtn = document.querySelector("#aiSelectAllBtn");
const aiClearBtn = document.querySelector("#aiClearBtn");

let aiItems = [];
let aiSelected = new Set();

function moneySGD(n){
  const num = Number(n || 0);
  return "S$" + num.toFixed(2);
}
function escapeHtml(s){
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/\'/g, "&#039;");
}

function openAIModal(){
  setUploadBtnActive(true);
  if (!aiModal || !aiBackdrop) return;
  aiBackdrop.hidden = false;
  aiModal.hidden = false;
  aiModal.setAttribute("aria-modal", "true");
  document.body.style.overflow = "hidden";
}

function closeAIModal(){
  setUploadBtnActive(false);
  if (!aiModal || !aiBackdrop) return;
  aiBackdrop.hidden = true;
  aiModal.hidden = true;
  aiModal.setAttribute("aria-modal", "false");
  document.body.style.overflow = "";
  aiItems = [];
  aiSelected = new Set();
  if (aiList) aiList.innerHTML = "";
  updateAIStats();
}

function renderLoading(){
  if (!aiList) return;
  aiList.innerHTML = `
    <div class="ci-ai-skel">
      <div class="bar" style="width:65%"></div>
      <div class="bar" style="width:90%"></div>
      <div class="bar" style="width:80%"></div>
      <div class="bar" style="width:55%"></div>
    </div>
  `;
  if (aiDetectedTitle) aiDetectedTitle.textContent = "Detected Items (0/0 selected)";
  if (aiTotalText) aiTotalText.textContent = moneySGD(0);
  if (aiSelectedCount) aiSelectedCount.textContent = "0 items selected";
}

function updateAIStats(){
  const selectedCount = aiSelected.size;
  const totalCount = aiItems.length;
  let total = 0;
  aiItems.forEach((it, idx) => {
    if (aiSelected.has(String(idx))) total += Number(it.amount || 0);
  });
  if (aiDetectedTitle) aiDetectedTitle.textContent = `Detected Items (${selectedCount}/${totalCount} selected)`;
  if (aiTotalText) aiTotalText.textContent = moneySGD(total);
  if (aiSelectedCount) aiSelectedCount.textContent = `${selectedCount} item${selectedCount===1?"":"s"} selected`;
}

function renderAIItems(){
  if (!aiList) return;

  if (!aiItems.length){
    aiList.innerHTML = `<div style="padding:18px; color: var(--muted);">No catalogue items detected. Upload a PO/quote that contains item names from your Catalogue, or add items manually.</div>`;
    updateAIStats();
    return;
  }

  aiList.innerHTML = aiItems.map((it, idx) => {
    const conf = Number(it.confidence || 0);
    const checked = aiSelected.has(String(idx)) ? "checked" : "";
    return `
      <div class="ci-ai-item" data-idx="${idx}">
        <input type="checkbox" class="aiChk" ${checked} aria-label="Select item">
        <div class="ci-ai-item-main">
          <div class="ci-ai-item-name">${escapeHtml(it.description || "")}</div>
          <div class="ci-ai-item-grid">
            <div>
              <div class="k">Quantity</div>
              <div class="v">${escapeHtml(String(it.quantity ?? 1))}</div>
            </div>
            <div>
              <div class="k">Rate</div>
              <div class="v">${moneySGD(it.rate || 0)}</div>
            </div>
            <div>
              <div class="k">Amount</div>
              <div class="v ci-ai-item-amt">${moneySGD(it.amount || 0)}</div>
            </div>
          </div>
        </div>
        <div class="ci-ai-badgeconf">${conf ? conf + "% confident" : "Review"}</div>
      </div>
    `;
  }).join("");

  aiList.querySelectorAll(".ci-ai-item").forEach((card)=>{
    card.addEventListener("click",(e)=>{
      if(e.target.tagName.toLowerCase()==="input") return;
      const idx = card.getAttribute("data-idx");
      const chk = card.querySelector(".aiChk");
      chk.checked = !chk.checked;
      if(chk.checked) aiSelected.add(String(idx));
      else aiSelected.delete(String(idx));
      updateAIStats();
    });
  });
  aiList.querySelectorAll(".aiChk").forEach((chk) => {
    chk.addEventListener("change", (e) => {
      const card = e.target.closest(".ci-ai-item");
      const idx = card ? card.getAttribute("data-idx") : null;
      if (idx == null) return;
      if (e.target.checked) aiSelected.add(String(idx));
      else aiSelected.delete(String(idx));
      updateAIStats();
    });
  });

  updateAIStats();
}

async function runPOReader(file){
  const fd = new FormData();
  fd.append("file", file);

  const res = await fetch("/api/po-reader", { method: "POST", body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok){
    throw new Error(data.error || "Upload failed");
  }
  return data;
}

function setFileMeta(file){
  if (!aiDocName || !aiDocMeta) return;
  aiDocName.textContent = file ? file.name : "No file selected";
  const kb = file ? (file.size / 1024) : 0;
  aiDocMeta.textContent = file ? `${kb.toFixed(1)} KB` : "—";
}

if (uploadBtn && poFileInput){
  uploadBtn.addEventListener("click", () => {
    poFileInput.value = "";
    poFileInput.click();
  });

  poFileInput.addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    setFileMeta(file);
    openAIModal();
    renderLoading();

    try{
      const data = await runPOReader(file);
      aiItems = Array.isArray(data.line_items) ? data.line_items : [];
      aiSelected = new Set();
      renderAIItems();
    }catch(err){
      if (aiList) aiList.innerHTML = `<div style="padding:18px; color:#b91c1c; font-weight:700;">${escapeHtml(err.message || "Failed to read document")}</div>`;
      updateAIStats();
    }
  });
}

if (aiSelectAllBtn){
  aiSelectAllBtn.addEventListener("click", () => {
    aiSelected = new Set(aiItems.map((_, i) => String(i)));
    renderAIItems();
  });
}

if (aiClearBtn){
  aiClearBtn.addEventListener("click", () => {
    aiSelected = new Set();
    renderAIItems();
  });
}

if (aiAddBtn){
  aiAddBtn.addEventListener("click", () => {
    if (!aiSelected.size){
      toast("Select at least 1 item");
      return;
    }

    aiItems.forEach((it, idx) => {
      if (!aiSelected.has(String(idx))) return;
      const newId = addItemRow({
        description: it.description || "",
        quantity: it.quantity ?? 1,
        unit_price: Number(it.rate ?? 0)
      });
    });

    renderItems();
    closeAIModal();
    toast("Items added to invoice");
  });
}

if (aiClose) aiClose.addEventListener("click", closeAIModal);
if (aiCancelBtn) aiCancelBtn.addEventListener("click", closeAIModal);
if (aiBackdrop) aiBackdrop.addEventListener("click", closeAIModal);



async function init(){
  // defaults
  $("#issueDate").value = todayISO();
  $("#dueDate").value = addDaysISO($("#issueDate").value, 30);

  await Promise.all([loadClients(), loadNextNumber(), loadProducts()]);
  renderSelectedClientUI();
  
}
init().catch(()=> toast("Failed to load"));
