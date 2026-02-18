const search = document.getElementById("searchInput");
const dateFrom = document.getElementById("dateFrom");
const dateTo = document.getElementById("dateTo");
const tableBody = document.querySelector(".fv-table tbody");
const statusCards = document.querySelectorAll(".fv-stat-card");
const statusPills = document.querySelectorAll(".fv-pill");
let currentStatus = document.querySelector(".fv-pill.active")?.dataset.status || "all";
const currentUserRole = (window.currentUserRole || '').toLowerCase();
const isCurrentUserAdmin = currentUserRole === 'admin';

// Update date placeholder dynamically as user types
function updateDatePlaceholder(input) {
  // Get current value
  const value = input.value;
  const template = "dd/mm/yyyy";
  
  // Count non-slash characters
  let charCount = 0;
  let displayValue = "";
  let templateIndex = 0;
  
  for (let i = 0; i < value.length; i++) {
    if (value[i] === '/') {
      displayValue += '/';
      // Skip slashes in template
      while (templateIndex < template.length && template[templateIndex] === '/') {
        templateIndex++;
      }
    } else {
      charCount++;
      displayValue += value[i];
      templateIndex++;
    }
  }
  
  // Add remaining placeholder
  let remaining = "";
  while (templateIndex < template.length) {
    remaining += template[templateIndex];
    templateIndex++;
  }
  
  input.placeholder = remaining;
}

// Throttle for date validation toasts (prevent spam)
let lastDateErrorToast = 0;
function showDateError(message) {
  const now = Date.now();
  if (now - lastDateErrorToast > 2000) { // Only show once per 2 seconds
    if (typeof showError === 'function') {
      showError(message);
    }
    lastDateErrorToast = now;
  }
}

// Validate date parts to prevent invalid dates (e.g., day 32, month 13, Feb 30)
function validateDateInput(value) {
  const parts = value.split('/');
  
  // Month validation first (positions 3-4): must be 01-12
  if (parts[1] && parts[1].length === 2) {
    const month = parseInt(parts[1]);
    if (month < 1 || month > 12) {
      // Show error toast (throttled)
      showDateError('Invalid month. Please enter a month between 01 and 12.');
      // Remove the invalid month digit (keep day and first slash)
      return parts[0] + '/' + parts[1].substring(0, 1);
    }
  }
  
  // Day validation with month-specific limits
  if (parts[0] && parts[0].length === 2) {
    const day = parseInt(parts[0]);
    let maxDay = 31;
    let monthName = '';
    
    // If we have a valid month, check month-specific day limits
    if (parts[1] && parts[1].length === 2) {
      const month = parseInt(parts[1]);
      const monthNames = ['', 'January', 'February', 'March', 'April', 'May', 'June', 
                          'July', 'August', 'September', 'October', 'November', 'December'];
      monthName = monthNames[month] || '';
      
      if ([4, 6, 9, 11].includes(month)) {
        maxDay = 30; // April, June, Sept, Nov have 30 days
      } else if (month === 2) {
        // February: check for leap year if we have the year
        if (parts[2] && parts[2].length === 4) {
          const year = parseInt(parts[2]);
          const isLeapYear = (year % 4 === 0 && year % 100 !== 0) || (year % 400 === 0);
          maxDay = isLeapYear ? 29 : 28;
        } else {
          maxDay = 29; // Allow 29 until we know the year
        }
      }
    }
    
    if (day < 1 || day > maxDay) {
      // Show error toast with specific message (throttled)
      if (monthName) {
        showDateError(`${monthName} has a maximum of ${maxDay} days.`);
      } else {
        showDateError(`Invalid day. Please enter a day between 01 and ${maxDay}.`);
      }
      return value.substring(0, 1); // Keep only first digit
    }
  }
  
  return value;
}

// Add input listeners for dynamic placeholder and validation
if (dateFrom) {
  dateFrom.addEventListener('input', function(e) {
    // Only allow numbers and forward slashes - IMMEDIATE
    let value = this.value.replace(/[^0-9\/]/g, '');
    
    // Validate date parts (prevent 32, 13, etc.)
    value = validateDateInput(value);
    
    // Allow deletion - only auto-add slashes if user hasn't just deleted
    const previousLength = this.getAttribute('data-prev-length') || 0;
    const currentLength = value.length;
    const isDeleting = currentLength < previousLength;
    
    // Auto-add slashes (but not if user is deleting)
    if (!isDeleting) {
      if (value.length === 2 && !value.includes('/')) {
        value = value + '/';
      } else if (value.length === 5 && (value.match(/\//g) || []).length === 1) {
        value = value + '/';
      }
    }
    
    // Max length 10 (dd/mm/yyyy)
    if (value.length > 10) {
      value = value.substring(0, 10);
    }
    
    this.value = value;
    this.setAttribute('data-prev-length', value.length);
    updateDatePlaceholder(this);
  });
  
  dateFrom.addEventListener('change', function() {
    // Refresh filter when user is done editing (immediate update, no debounce)
    applyFilter(currentStatus, search.value);
  });
  
  dateFrom.addEventListener('focus', function() {
    if (!this.value) {
      this.placeholder = "dd/mm/yyyy";
    } else {
      updateDatePlaceholder(this);
    }
  });
  dateFrom.addEventListener('blur', function() {
    this.placeholder = "dd/mm/yyyy";
  });
}

if (dateTo) {
  dateTo.addEventListener('input', function(e) {
    // Only allow numbers and forward slashes - IMMEDIATE
    let value = this.value.replace(/[^0-9\/]/g, '');
    
    // Validate date parts (prevent 32, 13, etc.)
    value = validateDateInput(value);
    
    // Allow deletion - only auto-add slashes if user hasn't just deleted
    const previousLength = this.getAttribute('data-prev-length') || 0;
    const currentLength = value.length;
    const isDeleting = currentLength < previousLength;
    
    // Auto-add slashes (but not if user is deleting)
    if (!isDeleting) {
      if (value.length === 2 && !value.includes('/')) {
        value = value + '/';
      } else if (value.length === 5 && (value.match(/\//g) || []).length === 1) {
        value = value + '/';
      }
    }
    
    // Max length 10 (dd/mm/yyyy)
    if (value.length > 10) {
      value = value.substring(0, 10);
    }
    
    this.value = value;
    this.setAttribute('data-prev-length', value.length);
    updateDatePlaceholder(this);
  });
  
  dateTo.addEventListener('change', function() {
    // Refresh filter when user is done editing (immediate update, no debounce)
    applyFilter(currentStatus, search.value);
  });
  
  dateTo.addEventListener('focus', function() {
    if (!this.value) {
      this.placeholder = "dd/mm/yyyy";
    } else {
      updateDatePlaceholder(this);
    }
  });
  dateTo.addEventListener('blur', function() {
    this.placeholder = "dd/mm/yyyy";
  });
}

// Convert dd/mm/yyyy to yyyy-mm-dd for API
function convertDateForAPI(ddmmyyyy) {
  if (!ddmmyyyy || ddmmyyyy.trim() === '') return '';
  
  const parts = ddmmyyyy.split('/');
  if (parts.length !== 3) return '';
  
  const day = parseInt(parts[0]);
  const month = parseInt(parts[1]);
  const year = parseInt(parts[2]);
  
  // Basic validation
  if (isNaN(day) || isNaN(month) || isNaN(year) || 
      day < 1 || day > 31 || month < 1 || month > 12 || year < 1900) {
    return '';
  }
  
  return `${year}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
}

function applyFilter(status, q) {
  currentStatus = status;
  
  // Show loading state
  tableBody.innerHTML = `
    <tr>
      <td colspan="7" class="text-center py-5">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
      </td>
    </tr>
  `;
  
  // Update active UI
  updateActiveUI(status);
  
  // Build query string with date parameters
  const params = new URLSearchParams();
  params.append('status', status);
  params.append('q', q || '');
  
  // Convert dd/mm/yyyy to yyyy-mm-dd for API
  if (dateFrom.value) {
    const apiDateFrom = convertDateForAPI(dateFrom.value);
    if (apiDateFrom) {
      params.append('date_from', apiDateFrom);
    } else {
      showError('Invalid "From Date" format. Use dd/mm/yyyy');
      return;
    }
  }
  if (dateTo.value) {
    const apiDateTo = convertDateForAPI(dateTo.value);
    if (apiDateTo) {
      params.append('date_to', apiDateTo);
    } else {
      showError('Invalid "To Date" format. Use dd/mm/yyyy');
      return;
    }
  }
  
  // Make AJAX request
  fetch(`/invoice-delivery/filter?${params.toString()}`)
    .then(response => response.json()) // Parse JSON response
    .then(data => {
      renderInvoices(data.invoices);
      updateCounts(data.counts);
    })
    .catch(error => {
      console.error('Error:', error);
      tableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-5 text-danger">
            Error loading invoices. Please try again.
          </td>
        </tr>
      `;
    });
}

function updateActiveUI(status) {
  // Update pills
  statusPills.forEach(pill => {
    if (pill.dataset.status === status) {
      pill.classList.add('active');
    } else {
      pill.classList.remove('active');
    }
  });
  
  // Update status cards
  statusCards.forEach(card => { // Updated to use dataset
    if (card.dataset.status === status) {
      card.classList.add('active');
    } else {
      card.classList.remove('active');
    }
  });
}

function renderInvoices(invoices) {
  // Remove the existing no-invoices row if it exists
  const existingNoInvoicesRow = document.getElementById('no-invoices-row');
  if (existingNoInvoicesRow) {
    existingNoInvoicesRow.remove();
  }
  
  if (invoices.length === 0) { // No invoices found case
    tableBody.innerHTML = `
      <tr id="no-invoices-row">
        <td colspan="7" class="text-center py-5 text-muted">
          <i class="bi bi-inbox fs-1"></i>
          <div class="mt-3">No invoices found</div>
        </td>
      </tr>
    `;
    return;
  }
  
  // Render invoice rows normally
  const rows = invoices.map(invoice => `
    <tr class="fv-row" data-invoice-id="${invoice.id}">
      <td class="text-primary fw-semibold">${invoice.invoice_number}</td>
      <td>${invoice.client_name}</td>
      <td>${invoice.email}</td>
      <td>${formatDate(invoice.sent_date)}</td>
      <td>${formatDate(invoice.opened_date)}</td>
      <td>
        <span class="fv-status ${invoice.status}">
          ${invoice.status.charAt(0).toUpperCase() + invoice.status.slice(1)}
        </span>
      </td>
      <td>
        <button class="btn-resend-pill" data-invoice-id="${invoice.id}">Resend</button>
      </td>
    </tr>
  `).join('');
  
  tableBody.innerHTML = rows;
}

function updateCounts(counts) {
  // Update status card values
  document.querySelector('[data-status="all"] .fs-3').textContent = counts.total || 0;
  document.querySelector('[data-status="delivered"] .fs-3').textContent = counts.delivered || 0;
  document.querySelector('[data-status="opened"] .fs-3').textContent = counts.opened || 0;
  document.querySelector('[data-status="pending"] .fs-3').textContent = counts.pending || 0;
  document.querySelector('[data-status="failed"] .fs-3').textContent = counts.failed || 0;
  
  // Update pill counts
  statusPills.forEach(pill => {
    const status = pill.dataset.status;
    let count;
    if (status === 'all') {
      count = counts.total || 0;
    } else {
      count = counts[status] || 0;
    }
    
    const countSpan = pill.querySelector('.pill-count');
    if (countSpan) {
      countSpan.textContent = `(${count})`;
    }
  });
}

// Debounce function
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Event Listeners
const debouncedApplyFilter = debounce(() => {
  applyFilter(currentStatus, search.value);
}, 150);

search.addEventListener("input", debouncedApplyFilter);

// Date filter change listeners
dateFrom.addEventListener("change", () => {
  applyFilter(currentStatus, search.value);
});

dateTo.addEventListener("change", () => {
  applyFilter(currentStatus, search.value);
});

// Status pill clicks
statusPills.forEach(pill => {
  pill.onclick = () => applyFilter(pill.dataset.status, search.value);
});

// Status card clicks
statusCards.forEach(card => {
  card.onclick = () => applyFilter(card.dataset.status, search.value);
});

// Resend function - REMOVE CONFIRM FROM HERE
function resendInvoice(id) {
  console.log(`[Resend] Starting resend for invoice ${id}`);
  fetch(`/invoice-delivery/${id}/resend`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    }
  })
  .then(response => {
    console.log(`[Resend] Got response status: ${response.status}`);
    return response.json();
  })
  .then(data => {
    console.log(`[Resend] Got response data:`, data);
    if (data.success) {
      const emailMsg = data.email ? ` to ${data.email}` : '';
      console.log(`[Resend] Success! Message: ${emailMsg}`);
      showSuccess(`Invoice queued for resend${emailMsg}`);
      if (data.deliverability_warning) {
        showSuccess(`Deliverability notice: ${data.deliverability_warning}`);
      }
      // Refresh the current filter
      applyFilter(currentStatus, search.value);
    } else {
      console.error(`[Resend] Error in response:`, data.error);
      showError(data.error || 'Error resending invoice');
    }
  })
  .catch(error => {
    console.error('[Resend] Fetch error:', error);
    showError('Error resending invoice');
  });
}

// Event listener for resend buttons using data attributes
document.addEventListener('click', function(event) {
  if (event.target.classList.contains('btn-resend-pill')) {
    event.stopPropagation(); // Prevent event from bubbling up
    
    const invoiceId = event.target.dataset.invoiceId;
    const invoiceNumber = event.target.closest('tr')?.querySelector('.text-primary')?.textContent || 'INV-' + invoiceId;
    if (invoiceId) {
      showResendConfirm(parseInt(invoiceId), invoiceNumber);
    }
  }
});

// Event listener for row clicks - simplified version
tableBody.addEventListener("click", function(e) {
  // If clicking on resend button, do nothing (let resend function handle it)
  if (e.target.classList.contains('btn-resend-pill') || 
      e.target.closest('.btn-resend-pill')) {
    return;
  }
  
  // Find the closest table row
  const row = e.target.closest('tr.fv-row');
  if (!row) return;
  
  const invoiceId = row.dataset.invoiceId;
  if (!invoiceId) {
    console.error('No invoice ID found on row');
    return;
  }

  openInvoiceModalLoading(invoiceId);
  
  console.log('Fetching invoice details for ID:', invoiceId);
  
  fetch(`/invoice-delivery/${invoiceId}`)
    .then(res => {
      if (!res.ok) throw new Error('Network response was not ok');
      return res.json();
    })
    .then(data => {
      console.log('Invoice data received:', data);
      openInvoiceModal(data);
    })
    .catch(error => {
      console.error('Error loading invoice details:', error);
      closeInvoiceModal();
      showError("Failed to load invoice details. Please try again.");
    });
});

// ... existing code ...

function openInvoiceModalLoading(invoiceId) {
  document.getElementById("modalInvoiceNumber").textContent = `Loading INV-${invoiceId}...`;
  document.getElementById("modalClientEmail").textContent = "Fetching invoice details";

  const statusEl = document.getElementById("modalStatus");
  statusEl.className = "fv-status pending";
  statusEl.textContent = "Loading";

  document.getElementById("modalEmail").textContent = "-";
  document.getElementById("modalOpenedDateTime").textContent = "-";
  document.getElementById("modalIssueDate").textContent = "-";
  document.getElementById("modalDueDate").textContent = "-";
  document.getElementById("modalAmount").textContent = "$0.00";
  document.getElementById("modalClientName").textContent = "-";
  document.getElementById("modalBusinessLocation").textContent = "-";

  const itemsContainer = document.getElementById("modalItems");
  const totalsContainer = document.getElementById("modalTotals");
  itemsContainer.innerHTML = `
    <tr>
      <td colspan="4" class="text-center py-4 text-muted">
        <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
        Loading invoice details...
      </td>
    </tr>
  `;
  totalsContainer.innerHTML = `
    <tr><td colspan="3" class="text-end fw-semibold">Subtotal</td><td class="text-end fw-semibold">-</td></tr>
    <tr><td colspan="3" class="text-end fw-semibold">GST (9%)</td><td class="text-end fw-semibold">-</td></tr>
    <tr><td colspan="3" class="text-end fw-bold">Total</td><td class="text-end fw-bold">-</td></tr>
  `;

  const webhookNotice = document.getElementById("webhookDisabledNotice");
  const manualActionsCard = document.getElementById("manualActionsCard");
  if (webhookNotice) webhookNotice.style.display = 'none';
  if (manualActionsCard) manualActionsCard.style.display = 'none';

  const modal = document.getElementById("invoiceModal");
  if (modal) {
    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
  }
}

function openInvoiceModal(data) {
  console.log('Opening modal with data:', data);
  
  // Update header
  document.getElementById("modalInvoiceNumber").textContent = data.invoice_number || 'N/A';
  document.getElementById("modalClientEmail").textContent = `Client: ${data.client_name || 'N/A'}`;
  
  // Update delivery info
  const statusEl = document.getElementById("modalStatus");
  if (data.status) {
    statusEl.className = `fv-status ${data.status}`;
    statusEl.textContent = data.status.charAt(0).toUpperCase() + data.status.slice(1);
  }
  
  document.getElementById("modalEmail").textContent = data.email || 'N/A';
  
  // Format opened date/time
  document.getElementById("modalOpenedDateTime").textContent = formatDateTime(data.opened_date) || 'Not opened yet';
  
  // Update invoice details
  document.getElementById("modalIssueDate").textContent = formatDate(data.issue_date);
  document.getElementById("modalDueDate").textContent = formatDate(data.due_date);
  document.getElementById("modalAmount").textContent = formatCurrency(data.total) || '$0.00';
  
  // Update client information
  document.getElementById("modalClientName").textContent = data.client_name || 'N/A';
  document.getElementById("modalBusinessLocation").textContent = data.address || 'N/A';
  
  // Update items table
  const itemsContainer = document.getElementById("modalItems");
  const totalsContainer = document.getElementById("modalTotals");
  const gstRate = typeof data.gst_rate === 'number' ? data.gst_rate : 0.09;
  const backendSubtotal = parseCurrency(data.subtotal);
  const backendTax = parseCurrency(data.tax);
  const backendTotal = parseCurrency(data.total);

  let subtotal = 0;
  let tax = backendTax;
  let total = backendTotal;
  
  if (data.items && Array.isArray(data.items) && data.items.length > 0) {
    // Clear existing
    itemsContainer.innerHTML = '';
    totalsContainer.innerHTML = '';
    
    // Add each item with proper calculation
    data.items.forEach(item => {
      // Parse values safely
      const qty = parseInt(item.qty) || 0;
      const rate = parseFloat((item.rate || '').replace(/[^0-9.-]+/g, '')) || 0;
      let amount = 0;
      
      // Calculate amount = qty × rate
      amount = qty * rate;
      
      // If backend provides amount, use it (but recalculate to verify)
      if (item.amount) {
        const backendAmount = parseFloat((item.amount || '').replace(/[^0-9.-]+/g, '')) || 0;
        // Log discrepancy for debugging
        if (Math.abs(backendAmount - amount) > 0.01) {
          console.warn(`Amount mismatch for ${item.description}: Calculated ${amount}, Backend ${backendAmount}`);
          // Use backend amount but flag in development
          if (app.config.debug) {
            amount = backendAmount;
          }
        }
      }
      
      subtotal += amount;
      
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${escapeHtml(item.description || '')}</td>
        <td class="text-center">${qty.toLocaleString()}</td>
        <td class="text-end">${formatCurrency(rate)}</td>
        <td class="text-end">${formatCurrency(amount)}</td>
      `;
      itemsContainer.appendChild(row);
    });
    
    // Use backend tax calculation if available, otherwise calculate
    tax = data.tax ? 
      parseFloat((data.tax || '').replace(/[^0-9.-]+/g, '')) || 0 :
      subtotal * gstRate;
    
    total = data.total ? 
      parseFloat((data.total || '').replace(/[^0-9.-]+/g, '')) || 0 :
      subtotal + tax;
    
    // Verify calculation matches backend
    const calculatedTotal = subtotal + tax;
    if (Math.abs(total - calculatedTotal) > 0.01) {
      console.warn(`Total mismatch: Backend ${total}, Calculated ${calculatedTotal}`);
      // In production, use backend total but log discrepancy
    }
    
    // Update total amount in header
    document.getElementById("modalAmount").textContent = formatCurrency(total);
  } else {
    itemsContainer.innerHTML = `
      <tr>
        <td colspan="4" class="text-center py-4 text-muted">
          No items found for this invoice
        </td>
      </tr>
    `;
    // Fall back to backend values if items are missing
    subtotal = backendSubtotal;
    tax = backendTax || subtotal * gstRate;
    total = backendTotal || (subtotal + tax);
  }

  // Show totals even when items are missing
  totalsContainer.innerHTML = `
    <tr>
      <td colspan="3" class="text-end fw-semibold">Subtotal</td>
      <td class="text-end fw-semibold">${formatCurrency(subtotal)}</td>
    </tr>
    <tr>
      <td colspan="3" class="text-end fw-semibold">GST (${(gstRate * 100).toFixed(0)}%)</td>
      <td class="text-end fw-semibold">${formatCurrency(tax)}</td>
    </tr>
    <tr>
      <td colspan="3" class="text-end fw-bold">Total</td>
      <td class="text-end fw-bold">${formatCurrency(total)}</td>
    </tr>
  `;
  
  // Timeline removed per user request
  
  
  // Timeline removed per user request
  
  // Setup resend button
  const resendBtn = document.getElementById("modalResendBtn");
  if (resendBtn) {
    // Remove any existing listeners first
    const newResendBtn = resendBtn.cloneNode(true);
    resendBtn.parentNode.replaceChild(newResendBtn, resendBtn);
    
    // Add new listener
    newResendBtn.addEventListener('click', function(event) {
      event.stopPropagation();
      showResendConfirm(data.id, data.invoice_number);
    });
  }
  
  // Setup preview button
  const previewBtn = document.getElementById("modalPreviewBtn");
  if (previewBtn) {
    const newPreviewBtn = previewBtn.cloneNode(true);
    previewBtn.parentNode.replaceChild(newPreviewBtn, previewBtn);

    newPreviewBtn.addEventListener('click', function(event) {
      event.stopPropagation();
      previewInvoicePDF(data.id, data.invoice_number);
    });
  }
  
  // Handle webhook status and manual actions visibility
  const webhookStatus = data.webhook_status || {};
  const webhookState = webhookStatus.state || (data.webhook_enabled ? 'active' : 'disabled');
  const webhookConnected = webhookState === 'active';
  const webhookNotice = document.getElementById("webhookDisabledNotice");
  const webhookNoticeTitle = document.getElementById("webhookNoticeTitle");
  const webhookNoticeMessage = document.getElementById("webhookNoticeMessage");
  const webhookNoticeHint = document.getElementById("webhookNoticeHint");
  const manualActionsCard = document.getElementById("manualActionsCard");
  const markDeliveredBtn = document.getElementById("modalMarkDeliveredBtn2");
  const markPendingBtn = document.getElementById("modalMarkPendingBtn2");
  const markFailedBtn = document.getElementById("modalMarkFailedBtn2");
  
  // Hide notice and actions for opened invoices (link tracking works automatically)
  if (data.status === 'opened') {
    if (webhookNotice) webhookNotice.style.display = 'none';
    if (manualActionsCard) manualActionsCard.style.display = 'none';
  } else if (!webhookConnected) {
    if (webhookNoticeTitle && webhookNoticeMessage && webhookNoticeHint) {
      if (webhookState === 'unreachable') {
        webhookNoticeTitle.textContent = 'Manual Tracking Required (Webhook Unreachable)';
        webhookNoticeMessage.innerHTML = `
          Webhook URL is configured but currently <strong>unreachable</strong>. Until it recovers, manually verify delivery status from your
          <a href="https://dashboard.serversmtp.com/dashboard" target="_blank" class="alert-link">TurboSMTP Dashboard</a>.
        `;
        webhookNoticeHint.innerHTML = `<i class="bi bi-info-circle"></i> Once webhook connectivity is restored, automatic delivery updates resume.`;
      } else {
        webhookNoticeTitle.textContent = 'Manual Tracking Required (Webhook Invalid/Disabled)';
        if (isCurrentUserAdmin) {
          webhookNoticeMessage.innerHTML = `
            Webhook configuration is <strong>invalid or disabled</strong>. Use a valid public <code>/webhooks/turbosmtp</code> endpoint in
            <a href="/settings" class="alert-link">Settings</a>, then manually verify delivery status from your TurboSMTP Dashboard meanwhile.
          `;
        } else {
          webhookNoticeMessage.innerHTML = `
            Webhook configuration is <strong>invalid or disabled</strong>. Please contact your administrator to update the webhook setup.
            Meanwhile, manually verify delivery status from your
            <a href="https://dashboard.serversmtp.com/dashboard" target="_blank" class="alert-link">TurboSMTP Dashboard</a>.
          `;
        }
        webhookNoticeHint.innerHTML = `<i class="bi bi-info-circle"></i> Only <strong>opened invoices</strong> (link clicks) are tracked automatically.`;
      }
    }

    // Webhooks disabled - show notice and manual action buttons (if status is appropriate)
    if (webhookNotice) {
      webhookNotice.style.display = 'flex';
    }
    
    // Show manual actions card for pending invoices only
    if (data.status === 'pending') {
      if (manualActionsCard) {
        manualActionsCard.style.display = 'block';
      }
      
      // Setup buttons based on current status
      // Pending only: Can mark as Delivered or Failed
      if (markDeliveredBtn) {
        if (data.status === 'pending') {
          const newMarkDeliveredBtn = markDeliveredBtn.cloneNode(true);
          markDeliveredBtn.parentNode.replaceChild(newMarkDeliveredBtn, markDeliveredBtn);
          newMarkDeliveredBtn.addEventListener('click', function(event) {
            event.stopPropagation();
            markInvoiceDelivered(data.id, data.invoice_number);
          });
          newMarkDeliveredBtn.style.display = 'inline-block';
        } else {
          markDeliveredBtn.style.display = 'none';
        }
      }
      
      // Hide mark as pending button (only used for pending status)
      if (markPendingBtn) {
        markPendingBtn.style.display = 'none';
      }
      
      // Pending: Can mark as failed
      if (markFailedBtn) {
        if (data.status === 'pending') {
          const newMarkFailedBtn = markFailedBtn.cloneNode(true);
          markFailedBtn.parentNode.replaceChild(newMarkFailedBtn, markFailedBtn);
          newMarkFailedBtn.addEventListener('click', function(event) {
            event.stopPropagation();
            markInvoiceFailed(data.id, data.invoice_number);
          });
          newMarkFailedBtn.style.display = 'inline-block';
        } else {
          markFailedBtn.style.display = 'none';
        }
      }
    } else {
      // For other statuses, hide manual actions card
      if (manualActionsCard) {
        manualActionsCard.style.display = 'none';
      }
    }
  } else {
    // Webhooks enabled - hide notice and manual actions
    if (webhookNotice) {
      webhookNotice.style.display = 'none';
    }
    if (manualActionsCard) {
      manualActionsCard.style.display = 'none';
    }
  }
  
  // Show modal
  const modal = document.getElementById("invoiceModal");
  if (modal) {
    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
  }
}

// Utility functions for production use
function formatCurrency(value) {
  if (typeof value === 'string') {
    // Remove non-numeric characters except decimal point
    value = parseFloat(value.replace(/[^0-9.-]+/g, '')) || 0;
  }
  
  // Handle rounding errors
  value = Math.round(value * 100) / 100;
  
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function parseCurrency(text) {
  if (!text) return 0;
  return parseFloat(text.replace(/[^0-9.-]+/g, '')) || 0;
}

// ... rest of existing code ...

// Add this function to close the modal
function closeInvoiceModal() {
  const modal = document.getElementById("invoiceModal");
  if (modal) {
    modal.style.display = "none";
    document.body.style.overflow = "auto";
  }
}

// Add event listener for close button
document.addEventListener('DOMContentLoaded', function() {
  const closeBtn = document.querySelector('[data-bs-dismiss="modal"]');
  if (closeBtn) {
    closeBtn.addEventListener('click', closeInvoiceModal);
  }
  
  // Also listen for any close buttons with class 'btn-close'
  const closeButtons = document.querySelectorAll('.btn-close, .modal-close');
  closeButtons.forEach(btn => {
    btn.addEventListener('click', closeInvoiceModal);
  });
});

// Also add event listener for Escape key
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    closeInvoiceModal();
  }
});

// Close modal when clicking outside of it
document.getElementById("invoiceModal").addEventListener('click', function(event) {
  if (event.target === this) {
    closeInvoiceModal();
  }
});

// Resend confirmation modal functions
function showResendConfirm(invoiceId, invoiceNumber) {
  const modal = document.getElementById('resendConfirmModal');
  const confirmBtn = document.getElementById('resendConfirmBtn');
  
  // Update modal message
  document.getElementById('resendConfirmMessage').innerHTML = `
    <i class="bi bi-exclamation-circle text-warning me-2"></i>
    Are you sure you want to resend invoice <strong>${invoiceNumber}</strong>?
  `;
  
  // Show modal
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  
  // Remove old listeners
  const newConfirmBtn = confirmBtn.cloneNode(true);
  confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
  
  // Add confirmation handler
  newConfirmBtn.addEventListener('click', function() {
    performResend(invoiceId);
  });
}

function closeResendConfirm() {
  const modal = document.getElementById('resendConfirmModal');
  modal.style.display = 'none';

  const invoiceModal = document.getElementById('invoiceModal');
  const invoiceModalOpen = invoiceModal && window.getComputedStyle(invoiceModal).display !== 'none';
  document.body.style.overflow = invoiceModalOpen ? 'hidden' : '';
}

function performResend(invoiceId) {
  const confirmBtn = document.getElementById('resendConfirmBtn');
  const originalBtnHtml = confirmBtn ? confirmBtn.innerHTML : '';
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Sending...';
  }

  fetch(`/invoice-delivery/${invoiceId}/resend`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    }
  })
  .then(response => response.json())
  .then(resendData => {
    if (resendData.success) {
      const emailMsg = resendData.email ? ` to ${resendData.email}` : '';
      showSuccess(`Invoice queued for resend${emailMsg}`);
      if (resendData.deliverability_warning) {
        showSuccess(`Deliverability notice: ${resendData.deliverability_warning}`);
      }
      applyFilter(currentStatus, search.value);
      closeResendConfirm();
      
      // Only reload invoice details if the modal is already open
      const invoiceModal = document.getElementById('invoiceDetailsModal');
      if (invoiceModal && invoiceModal.style.display === 'flex') {
        setTimeout(() => {
          fetch(`/invoice-delivery/${invoiceId}`)
            .then(res => res.json())
            .then(updatedData => {
              openInvoiceModal(updatedData);
            })
            .catch(e => {
              console.error('Error reloading invoice details:', e);
            });
        }, 500); // Wait 500ms for database to commit
      }
    } else {
      showError(`Failed to resend: ${resendData.error || 'Unknown error'}`);
    }
  })
  .catch(error => {
    console.error('Resend error:', error);
    showError('Error resending invoice. Please try again.');
  })
  .finally(() => {
    const latestConfirmBtn = document.getElementById('resendConfirmBtn');
    if (latestConfirmBtn) {
      latestConfirmBtn.disabled = false;
      latestConfirmBtn.innerHTML = originalBtnHtml || '<i class="bi bi-send"></i> Confirm Resend';
    }
  });
}

// Close resend modal when clicking on overlay
document.addEventListener('click', function(e) {
  const modal = document.getElementById('resendConfirmModal');
  if (e.target === modal) {
    closeResendConfirm();
  }
});

// Preview invoice PDF-like client view without marking invoice as opened
function previewInvoicePDF(invoiceId, invoiceNumber) {
  try {
    window.open(`/invoice-delivery/${invoiceId}/preview`, '_blank', 'noopener');
  } catch (error) {
    console.error('Preview error:', error);
    showError('Failed to open invoice preview. Please try again.');
  }
}

// Manual admin action: Mark invoice as delivered
function markInvoiceDelivered(invoiceId, invoiceNumber) {
  if (!confirm(`Confirm that invoice ${invoiceNumber} was successfully delivered?\n\nCheck your TurboSMTP dashboard first to verify delivery.`)) {
    return;
  }
  
  fetch(`/invoice-delivery/${invoiceId}/mark-delivered`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    }
  })
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  })
  .then(data => {
    if (data.success) {
      showSuccess(`Invoice ${invoiceNumber} marked as delivered`);
      applyFilter(currentStatus, search.value);
      // Reload invoice details to show updated timeline
      setTimeout(() => {
        fetch(`/invoice-delivery/${invoiceId}`)
          .then(res => res.json())
          .then(updatedData => {
            openInvoiceModal(updatedData);
          })
          .catch(e => {
            console.error('Error reloading invoice details:', e);
          });
      }, 500);
    } else {
      showError(`Failed to mark as delivered: ${data.message || 'Unknown error'}`);
    }
  })
  .catch(error => {
    console.error('Mark delivered error:', error);
    // Only show error if it's a network/server error, not a loadInvoiceDetails issue
    if (error.message && !error.message.includes('loadInvoiceDetails')) {
      showError('Error marking invoice as delivered. Please try again.');
    }
  });
}

// Manual admin action: Mark invoice as failed
function markInvoiceFailed(invoiceId, invoiceNumber) {
  if (!confirm(`Mark invoice ${invoiceNumber} as FAILED?\n\nThis indicates the delivery was unsuccessful and you need to verify the email address.`)) {
    return;
  }
  
  fetch(`/invoice-delivery/${invoiceId}/mark-failed`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    }
  })
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  })
  .then(data => {
    console.log('Mark as failed response:', data);
    if (data.success) {
      showSuccess(`Invoice ${invoiceNumber} marked as failed`);
      applyFilter(currentStatus, search.value);
      // Reload invoice details to show updated timeline
      setTimeout(() => {
        console.log('Reloading invoice details for ID:', invoiceId);
        fetch(`/invoice-delivery/${invoiceId}`)
          .then(res => res.json())
          .then(updatedData => {
            openInvoiceModal(updatedData);
          })
          .catch(e => {
            console.error('Error reloading invoice details:', e);
          });
      }, 500);
    } else {
      showError(`Failed to mark as failed: ${data.message || 'Unknown error'}`);
    }
  })
  .catch(error => {
    console.error('Mark failed error:', error);
    // Only show error if it's a network/server error, not a loadInvoiceDetails issue
    if (error.message && !error.message.includes('loadInvoiceDetails')) {
      showError('Error marking invoice as failed. Please try again.');
    }
  });
}

// Manual admin action: Mark invoice as pending
function markInvoicePending(invoiceId, invoiceNumber) {
  if (!confirm(`Reset invoice ${invoiceNumber} status to pending?\n\nThis will clear any delivery/failure status.`)) {
    return;
  }
  
  fetch(`/invoice-delivery/${invoiceId}/mark-pending`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    }
  })
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  })
  .then(data => {
    if (data.success) {
      showSuccess(`Invoice ${invoiceNumber} status reset to pending`);
      applyFilter(currentStatus, search.value);
      // Reload invoice details to show updated timeline
      setTimeout(() => {
        fetch(`/invoice-delivery/${invoiceId}`)
          .then(res => res.json())
          .then(updatedData => {
            openInvoiceModal(updatedData);
          })
          .catch(e => {
            console.error('Error reloading invoice details:', e);
          });
      }, 100);
    } else {
      showError(`Failed to reset status: ${data.message || 'Unknown error'}`);
    }
  })
  .catch(error => {
    console.error('Mark pending error:', error);
    // Only show error if it's a network/server error, not a loadInvoiceDetails issue  
    if (error.message && !error.message.includes('loadInvoiceDetails')) {
      showError('Error resetting invoice status. Please try again.');
    }
  });
}
