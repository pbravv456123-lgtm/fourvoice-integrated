// ===== APPROVALS PAGE JAVASCRIPT =====

console.log('Approvals JS loaded!');

// Global state variables for managing approvals data and UI state
let allInvoices = []; // Stores all invoice data fetched from the API
let currentFilter = 'all'; // Current active filter ('all', 'pending', 'approved', 'rejected', 'on-hold')
let currentAction = null; // Tracks the action being performed in the modal ('approve', 'reject', 'hold', 'acknowledge', 'resend')
let currentInvoiceId = null; // Stores the invoice ID currently being acted upon
let currentSearchQuery = ''; // Current search query from search input
let currentDateFrom = ''; // Current start date filter
let currentDateTo = ''; // Current end date filter
let currentRejectCategory = 'editable'; // editable | non-editable
let aiReviewStatusByInvoice = {};
let returnToInvoiceModalOnActionClose = false;
let inlinePhoneController = null;
const CURRENT_USER_ROLE = String(window.currentUserRole || 'employee').toLowerCase();
const IS_APPROVAL_ADMIN = CURRENT_USER_ROLE === 'admin';
const EMPLOYEE_ALLOWED_APPROVAL_ACTIONS = new Set(['acknowledge', 'resend']);
const DISPLAY_PAYMENT_TERMS = new Set(['Net 15', 'Net 30', 'Net 45', 'Due on Receipt']);

function resolvePaymentTerms(invoice) {
    const raw = String(invoice?.payment_terms || '').trim();
    if (DISPLAY_PAYMENT_TERMS.has(raw)) {
        return raw;
    }

    const submitted = invoice?.submitted_date ? new Date(invoice.submitted_date) : null;
    const due = invoice?.due_date ? new Date(invoice.due_date) : null;
    if (submitted && due && !isNaN(submitted.getTime()) && !isNaN(due.getTime())) {
        const dayDiff = Math.round((due - submitted) / (1000 * 60 * 60 * 24));
        if (dayDiff <= 0) return 'Due on Receipt';
        if (dayDiff === 15) return 'Net 15';
        if (dayDiff === 30) return 'Net 30';
        if (dayDiff === 45) return 'Net 45';
    }

    return 'Net 30';
}

function requireApprovalAdminPermission() {
    if (IS_APPROVAL_ADMIN) {
        return true;
    }
    showError('Only admin users can perform approvals actions.');
    return false;
}

function canRunApprovalAction(action) {
    if (IS_APPROVAL_ADMIN) {
        return true;
    }
    return EMPLOYEE_ALLOWED_APPROVAL_ACTIONS.has(action);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function buildPendingAIResultMarkup(aiState) {
    if (!aiState || !aiState.checked) {
        return '<div class="approval-ai-note">Run AI check to view detected issues before taking action.</div>';
    }

    const analysis = aiState.analysis || {};
    const title = escapeHtml(analysis.rejection_title || (analysis.should_reject ? 'Invoice Data Issue' : 'No Data Issues Found'));
    const description = escapeHtml(analysis.rejection_description || (analysis.should_reject
        ? 'Detected invoice issues requiring correction.'
        : 'Invoice data passed AI checks with no detectable issues.'));
    const issues = Array.isArray(analysis.specific_issues) ? analysis.specific_issues : [];

    const issuesMarkup = issues.length > 0
        ? `<ul class="approval-ai-issues">${issues.map(issue => `<li>${escapeHtml(issue)}</li>`).join('')}</ul>`
        : `<div class="approval-ai-empty">${analysis.should_reject ? 'AI did not return detailed issue lines. Review manually before taking action.' : 'AI did not detect clear invoice-data issues.'}</div>`;

    return `
        <div class="approval-ai-summary ${analysis.should_reject ? 'has-issues' : 'clear'}">
            <div class="approval-ai-title">${title}</div>
            <div class="approval-ai-desc">${description}</div>
            ${issuesMarkup}
        </div>
    `;
}

// Initialize page on load
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing approvals page...');
    document.body.style.overflow = '';
    
    // Setup search input listener
    const searchInput = document.getElementById('approvalsSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(function() {
            currentSearchQuery = this.value.toLowerCase();
            renderTable();
        }, 150));
    }
    
    // Convert dd/mm/yyyy to yyyy-mm-dd for filtering
    function convertDateForFilter(ddmmyyyy) {
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
    
    // Setup date filter listeners
    const dateFromInput = document.getElementById('approvalsDateFrom');
    const dateToInput = document.getElementById('approvalsDateTo');
    
    // Update date placeholder dynamically
    function updateDatePlaceholder(input) {
      const value = input.value;
      const template = "dd/mm/yyyy";
      
      let charCount = 0;
      let displayValue = "";
      let templateIndex = 0;
      
      for (let i = 0; i < value.length; i++) {
        if (value[i] === '/') {
          displayValue += '/';
          while (templateIndex < template.length && template[templateIndex] === '/') {
            templateIndex++;
          }
        } else {
          charCount++;
          displayValue += value[i];
          templateIndex++;
        }
      }
      
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

// Setup date filter event listeners
if (dateFromInput) {
    // Input validation - IMMEDIATE (no debounce) for character filtering
    dateFromInput.addEventListener('input', function(e) {
        // Only allow numbers and forward slashes - IMMEDIATELY
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
        
        // Max length 10
        if (value.length > 10) {
          value = value.substring(0, 10);
        }
        
        this.value = value;
        this.setAttribute('data-prev-length', value.length);
        updateDatePlaceholder(this);
    });
    
    // Filter refresh - DEBOUNCED for API calls
    dateFromInput.addEventListener('change', debounce(function(e) {
        const convertedDate = convertDateForFilter(this.value);
        if (this.value === '' || convertedDate) {
            currentDateFrom = convertedDate;
            renderTable();
        }
    }, 150));
    
    dateFromInput.addEventListener('focus', function() {
        if (!this.value) this.placeholder = "dd/mm/yyyy";
        else updateDatePlaceholder(this);
    });
    dateFromInput.addEventListener('blur', function() {
        this.placeholder = "dd/mm/yyyy";
    });
}
if (dateToInput) {
    // Input validation - IMMEDIATE (no debounce) for character filtering
    dateToInput.addEventListener('input', function(e) {
        // Only allow numbers and forward slashes - IMMEDIATELY
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
        
        // Max length 10
        if (value.length > 10) {
          value = value.substring(0, 10);
        }
        
        this.value = value;
        this.setAttribute('data-prev-length', value.length);
        updateDatePlaceholder(this);
    });
    
    // Filter refresh - DEBOUNCED for API calls
    dateToInput.addEventListener('change', debounce(function(e) {
        const convertedDate = convertDateForFilter(this.value);
        if (this.value === '' || convertedDate) {
            currentDateTo = convertedDate;
            renderTable();
        }
    }, 150));
    
    dateToInput.addEventListener('focus', function() {
        if (!this.value) this.placeholder = "dd/mm/yyyy";
        else updateDatePlaceholder(this);
    });
    dateToInput.addEventListener('blur', function() {
        this.placeholder = "dd/mm/yyyy";
    });
}
    
    loadApprovals(); // Fetch and display initial approvals data
});

// Load approvals data from API and initialize page
// Fetches all invoices from the backend and updates UI components
async function loadApprovals() { 
    console.log('Loading approvals from API...');
    try {
        const response = await fetch('/api/approvals'); // GET request to fetch approvals
        console.log('API response status:', response.status);
        if (!response.ok) {
            throw new Error('Failed to load approvals');
        }
        
        const data = await response.json(); // Parse JSON response
        console.log('API data received:', data);
        allInvoices = data.invoices || []; // Store invoices in global state
        console.log('Total invoices loaded:', allInvoices.length);
        
        updateCounts(); // Update status card counts
        renderTable(); // Render the invoices table
    } catch (error) {
        console.error('Error loading approvals:', error);
        showError('Failed to load invoices. Please refresh the page.'); // Show error notification
    }
}

// Update status counts for stat cards and filter pills
// Counts invoices by status and updates the UI display
function updateCounts() {
    const counts = {
        all: allInvoices.length,
        pending: 0,
        approved: 0,
        rejected: 0,
        'on-hold': 0
    };
    
    // Loop through all invoices and count by status
    allInvoices.forEach(invoice => {
        const status = invoice.approval_status;
        
        if (status === 'pending') {
            counts.pending++;
        } else if (status === 'approved') {
            counts.approved++;
        } else if (status === 'rejected') {
            counts.rejected++;
        } else if (status === 'on-hold') {
            counts['on-hold']++;
        }
    });
    
    // Update card counts
    document.getElementById('pending-count').textContent = counts.pending;
    document.getElementById('approved-count').textContent = counts.approved;
    document.getElementById('rejected-count').textContent = counts.rejected;
    document.getElementById('on-hold-count').textContent = counts['on-hold'];
    
    // Update pill counts
    document.querySelectorAll('.fv-pill').forEach(pill => {
        const filter = pill.getAttribute('data-filter');
        const originalText = pill.textContent.split(' (')[0]; // Get base text without count
        let count;
        
        if (filter === 'all') {
            count = counts.all;
        } else {
            count = counts[filter] || 0;
        }
        
        pill.textContent = `${originalText} (${count})`;
    });
}

// Filter invoices by status
// Updates the current filter and refreshes the UI to show only matching invoices
function filterByStatus(status) {
    currentFilter = status; // Update global filter state
    
    // Update active pill (not tab)
    document.querySelectorAll('.fv-pill').forEach(pill => {
        pill.classList.remove('active'); // Remove active class from all pills
    });
    const activePill = document.querySelector(`.fv-pill[data-filter="${status}"]`);
    if (activePill) {
        activePill.classList.add('active'); // Add active class to selected pill
    }
    
    // Update active card - highlights the corresponding stat card
    document.querySelectorAll('.fv-stat-card').forEach(card => {
        card.classList.remove('active'); // Remove active class from all cards
    });
    const activeCard = document.querySelector(`.fv-stat-card[data-status="${status}"]`); // Match data-status attribute
    if (activeCard) {
        activeCard.classList.add('active'); // Highlight active card
    }
    
    renderTable(); // Re-render table with filtered data
}

// Render the invoices table based on current filter
// Dynamically generates table rows with invoice data and action buttons
function renderTable() {
    const tbody = document.getElementById('approvals-table-body');
    const emptyState = document.getElementById('empty-state');
    const tableCard = document.querySelector('.card:has(.fv-table)');
    
    let filteredInvoices = allInvoices; // Start with all invoices
    
    // Apply status filter if not 'all'
    if (currentFilter !== 'all') {
        filteredInvoices = filteredInvoices.filter(invoice => 
            invoice.approval_status === currentFilter // Filter by selected status
        );
    }
    
    // Apply search filter
    if (currentSearchQuery) {
        filteredInvoices = filteredInvoices.filter(invoice => {
            const searchable = [
                invoice.invoice_number,
                invoice.client_name,
                invoice.email,
                invoice.submitted_by
            ].map(val => (val || '').toLowerCase()).join(' ');
            return searchable.includes(currentSearchQuery);
        });
    }
    
    // Apply date range filter
    if (currentDateFrom || currentDateTo) {
        filteredInvoices = filteredInvoices.filter(invoice => {
            const invoiceDate = invoice.submitted_date ? invoice.submitted_date.split(' ')[0] : '';
            
            if (currentDateFrom && invoiceDate < currentDateFrom) {
                return false;
            }
            if (currentDateTo && invoiceDate > currentDateTo) {
                return false;
            }
            return true;
        });
    }
    
    // Show empty state if no invoices after filtering
    if (filteredInvoices.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        if (tableCard) tableCard.style.display = 'none';
        return;
    }
    
    emptyState.style.display = 'none';
    if (tableCard) tableCard.style.display = 'block';
    
    // Build table rows HTML
    tbody.innerHTML = filteredInvoices.map(invoice => {
        const statusClass = `status-${invoice.approval_status}`;
        const avatar = invoice.submitted_by ? invoice.submitted_by.charAt(0).toUpperCase() : 'U';
        
        // Determine which action to show based on status and reason
        let actions = '';

        if (invoice.approval_status === 'on-hold') {
            // On Hold → show Resend button (green) only
            // Allows user to resubmit the invoice for approval
            actions = `
                <div class="fv-actions">
                    <button class="btn-resend-pill" onclick="resendInvoice(${invoice.id})">
                        Resend
                    </button>
                </div>
            `;
        } else if (invoice.approval_status === 'rejected') {
            // Rejected → show Re-edit or Acknowledge based on rejection reason category
            const reasonRaw = (invoice.approval_reason || '');
            const reasonLower = reasonRaw.toLowerCase();
            
            // Check for explicit editable tag or category suffix
            const isEditable = reasonRaw.includes('[EDITABLE]') || reasonLower.includes('| editable');
            
            if (isEditable) {
                // Editable issues can be fixed by editing (missing fields, spelling errors, invalid format)
                actions = `
                    <button class="btn-edit-pill" onclick="editInvoice(${invoice.id})">
                        Re-edit
                    </button>
                `;
            } else {
                // Non-editable issues require acknowledgement (logic errors, date validation, business rules)
                // User can only acknowledge and place on hold (cannot fix directly)
                actions = `
                    <button class="btn-acknowledge-pill" onclick="acknowledgeInvoice(${invoice.id})">
                        Acknowledge
                    </button>
                `;
            }
        } else if (invoice.approval_status === 'pending') {
            actions = IS_APPROVAL_ADMIN
                ? '<span class="text-muted small">Open invoice to review</span>'
                : '<span class="text-muted small">No actions available</span>';
        } else {
            actions = '<span class="text-muted small">No actions available</span>';
        }
        // Approved → no actions available
        
        return `
            <tr class="fv-row" data-invoice-id="${invoice.id}">
                <td>
                    <span class="text-primary fw-semibold">${invoice.invoice_number}</span>
                </td>
                <td>
                    <div class="fv-submitter">
                        <div class="fv-submitter-avatar">${avatar}</div>
                        <span class="fv-submitter-name">${invoice.submitted_by || 'Unknown'}</span>
                    </div>
                </td>
                <td>${invoice.client_name || 'N/A'}</td>
                <td>${formatDate(invoice.submitted_date)}</td>
                <td>${invoice.amount}</td>
                <td>
                    <span class="fv-status ${invoice.approval_status}">
                        ${invoice.approval_status.replace('-', ' ').charAt(0).toUpperCase() + invoice.approval_status.replace('-', ' ').slice(1)}
                    </span>
                </td>
                <td>${actions}</td>
            </tr>
        `;
    }).join('');
}

// Row click handler - open modal with details
// Allows clicking anywhere on a table row to open the invoice detail modal
document.addEventListener('click', function(e) {
    // If clicking on action button, do nothing here
    // Action buttons have their own onclick handlers
    if (e.target.closest('.fv-actions') ||
        e.target.classList.contains('btn-resend-pill') || 
        e.target.classList.contains('btn-edit-pill') ||
        e.target.classList.contains('btn-acknowledge-pill') ||
        e.target.classList.contains('btn-approve-pill') ||
        e.target.classList.contains('btn-reject-pill') ||
        e.target.classList.contains('btn-hold-pill') ||
        e.target.closest('.btn-resend-pill') ||
        e.target.closest('.btn-edit-pill') ||
        e.target.closest('.btn-acknowledge-pill') ||
        e.target.closest('.btn-approve-pill') ||
        e.target.closest('.btn-reject-pill') ||
        e.target.closest('.btn-hold-pill')) {
        return; // Exit early if action button was clicked
    }
    
    // Find the closest table row
    const row = e.target.closest('tr.fv-row');
    if (!row) return; // Not clicking on a table row
    
    // Get invoice ID from row dataset
    const invoiceId = parseInt(row.dataset.invoiceId);
    if (!invoiceId) return; // Invalid invoice ID
    
    // Open modal with invoice details
    console.log('Opening modal for invoice ID:', invoiceId);
    openApprovalModal(invoiceId); // Display the detail modal
});

// Open approval modal
// Displays a detailed modal with invoice information, status, and available actions
async function openApprovalModal(invoiceId) {
    const invoice = allInvoices.find(inv => inv.id === invoiceId); // Find invoice by ID
    if (!invoice) {
        console.error('Invoice not found:', invoiceId);
        return; // Exit if invoice not found
    }
    
    // Update modal header
    document.getElementById('modalInvoiceNumber').textContent = invoice.invoice_number || 'N/A';
    
    // Update client information (left side)
    document.getElementById('modalClientName').textContent = invoice.client_name || 'N/A';
    document.getElementById('modalClientEmail').textContent = invoice.email || 'No email provided';
    document.getElementById('modalClientPhone').textContent = invoice.phone || 'No phone provided';
    document.getElementById('modalBusinessLocation').textContent = invoice.address || 'No address provided';
    
    // Update invoice details (right side)
    document.getElementById('modalSubmittedDate').textContent = formatDate(invoice.submitted_date);
    document.getElementById('modalDueDate').textContent = formatDate(invoice.due_date);
    document.getElementById('modalPaymentTerms').textContent = resolvePaymentTerms(invoice);
    document.getElementById('modalAmount').textContent = invoice.amount || '$0.00';
    
    // Update status badge with current approval status
    const statusEl = document.getElementById('modalStatus'); // Get the status badge element
    const statusClass = invoice.approval_status; // Get current status (pending/approved/rejected/on-hold)
    statusEl.className = `fv-status ${statusClass}`; // Apply CSS class for styling based on status
    // Format status text: replace hyphens with spaces and capitalize first letter
    statusEl.textContent = invoice.approval_status.replace('-', ' ').charAt(0).toUpperCase() + invoice.approval_status.replace('-', ' ').slice(1);
    
    // Remove any existing status indicator block if present from older UI
    const existingWorkflow = document.getElementById('approval-workflow-indicator');
    if (existingWorkflow) {
        existingWorkflow.remove();
    }
    
    // Populate line items table
    const itemsBody = document.getElementById('modalItems');
    if (invoice.items && invoice.items.length > 0) {
        itemsBody.innerHTML = invoice.items.map(item => `
            <tr>
                <td>${item.description || 'No description'}</td>
                <td class="text-center">${item.quantity || 0}</td>
                <td class="text-end">$${parseFloat(item.rate || 0).toFixed(2)}</td>
                <td class="text-end">$${parseFloat(item.total || 0).toFixed(2)}</td>
            </tr>
        `).join('');
    } else {
        itemsBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No items found</td></tr>';
    }
    
    // Populate totals footer
    const totalsFooter = document.getElementById('modalTotals');
    totalsFooter.innerHTML = `
        <tr>
            <td colspan="3" class="text-end fw-semibold">Subtotal:</td>
            <td class="text-end">$${parseFloat(invoice.subtotal || 0).toFixed(2)}</td>
        </tr>
        <tr>
            <td colspan="3" class="text-end fw-semibold">Tax (9%):</td>
            <td class="text-end">$${parseFloat(invoice.tax || 0).toFixed(2)}</td>
        </tr>
        <tr>
            <td colspan="3" class="text-end fw-bold">Total:</td>
            <td class="text-end fw-bold">$${parseFloat(invoice.total || 0).toFixed(2)}</td>
        </tr>
    `;
    
    // Update notes section with invoice service details
    document.getElementById('modalNotes').textContent = invoice.notes || 'No service details available';

    const pendingAIValidationPanel = document.getElementById('pendingAIValidationPanel');
    const pendingAIValidationContent = document.getElementById('pendingAIValidationContent');
    const actionBtns = document.getElementById('modalActionButtons');

    // Handle rejection details section - only display for rejected invoices
    const rejectionContainer = document.getElementById('rejectionDetailsContainer');
    if (invoice.approval_status === 'rejected' && invoice.approval_reason) {
        rejectionContainer.style.display = 'block'; // Show rejection details section
        
        // Extract title from reason (first sentence or first part before colon)
        // Attempts to parse structured rejection reasons into title and description
        let reason = invoice.approval_reason;
        
        // Extract category if present (format: "reason | category") and remove it for display
        if (reason.includes(' | ')) {
            reason = reason.substring(0, reason.lastIndexOf(' | ')).trim();
        }
        
        // Remove category tags for display
        reason = reason.replace('[EDITABLE]', '').replace('[NOT_EDITABLE]', '').trim();
        
        let title = 'Issue'; // Default title
        let description = reason; // Full reason as fallback
        
        if (reason.includes(':')) {
            const parts = reason.split(':');
            title = parts[0].trim();
            description = parts.slice(1).join(':').trim();
        } else if (reason.includes('.')) {
            const sentences = reason.split('.');
            title = sentences[0].trim();
            description = sentences.slice(1).join('.').trim();
        }
        
        if (!title || title.toLowerCase().includes('rejection reason')) {
            title = description.split('. ')[0] || 'Issue';
        }

        document.getElementById('modalRejectionTitle').textContent = title;
        document.getElementById('modalRejectionReason').textContent = description || reason;
    } else {
        rejectionContainer.style.display = 'none';
    }
    
    // Update action buttons based on status
    // Dynamically shows appropriate action buttons in the modal footer
    let actionButton = ''; // Will contain HTML for action button
    
    if (invoice.approval_status === 'on-hold') {
        // On-hold invoices can be resent for approval
        actionButton = `
            <button class="btn approval-action-btn approval-resend-green" onclick="resendInvoice(${invoice.id}); closeApprovalModal();">
                Resend
            </button>
        `;
        if (pendingAIValidationPanel) pendingAIValidationPanel.style.display = 'none';
    } else if (invoice.approval_status === 'pending' && IS_APPROVAL_ADMIN) {
        const aiState = aiReviewStatusByInvoice[invoice.id] || {};
        const aiChecked = !!aiState.checked;
        const aiRecommendedAction = aiChecked ? (aiState.analysis?.should_reject ? 'reject' : 'approve') : '';
        const aiResultMarkup = buildPendingAIResultMarkup(aiState);

        if (pendingAIValidationPanel && pendingAIValidationContent) {
            pendingAIValidationPanel.style.display = 'block';
            pendingAIValidationContent.innerHTML = aiResultMarkup;
        }

        actionButton = `
            <button class="btn ${aiChecked ? 'btn-outline-success' : 'btn-outline-primary'} approval-action-btn" onclick="runPendingAICheck(${invoice.id})">
                <i class="bi ${aiChecked ? 'bi-check2-circle' : 'bi-stars'}"></i>
                ${aiChecked ? 'AI Checked' : 'Check with AI'}
            </button>
            <div class="approval-action-dropdown-wrap">
                <select id="pendingActionSelect" class="form-select approval-action-select" onchange="handlePendingActionSelection(${invoice.id}, this.value)">
                    <option value="">Actions</option>
                    <option value="approve" ${aiRecommendedAction === 'approve' ? 'selected' : ''}>🟢 Approve</option>
                    <option value="reject" ${aiRecommendedAction === 'reject' ? 'selected' : ''}>🔴 Reject</option>
                    <option value="hold">🟡 On Hold</option>
                </select>
                <button type="button" class="btn btn-primary approval-action-continue-btn" id="pendingActionContinueBtn" data-action="${aiRecommendedAction}" ${aiRecommendedAction ? '' : 'disabled'} onclick="submitPendingActionSelection(${invoice.id})">
                    Continue
                </button>
            </div>
        `;
    } else if (invoice.approval_status === 'pending' && !IS_APPROVAL_ADMIN) {
        if (pendingAIValidationPanel) pendingAIValidationPanel.style.display = 'none';
        actionButton = '';
    } else if (invoice.approval_status === 'rejected') {
        // Rejected invoices show Re-edit or Acknowledge based on explicit tags
        const reasonRaw = invoice.approval_reason || '';
        const reasonLower = reasonRaw.toLowerCase();
        const isEditable = reasonRaw.includes('[EDITABLE]') || reasonLower.includes('| editable');
        
        if (isEditable) {
            actionButton = `
                <button class="btn btn-primary" onclick="editInvoice(${invoice.id})">
                    Re-edit
                </button>
            `;
        } else {
            actionButton = `
                <button class="btn" style="background: #f97316; color: white; border: none;" onclick="acknowledgeInvoice(${invoice.id}); closeApprovalModal();">
                    Acknowledge
                </button>
            `;
        }

        if (pendingAIValidationPanel) pendingAIValidationPanel.style.display = 'none';
    } else {
        if (pendingAIValidationPanel) pendingAIValidationPanel.style.display = 'none';
    }
    
    // Add action button before close button
    actionBtns.innerHTML = `
        <button class="btn btn-outline-secondary" onclick="closeApprovalModal()">
            Close
        </button>
        <div class="approval-actions-group">
            ${actionButton}
        </div>
    `;
    
    // Show modal
    const modal = document.getElementById('approvalModal');
    if (modal) {
        modal.style.display = 'flex';
    }
    refreshModalScrollLock();
}

// Close approval modal
function closeApprovalModal() {
    const modal = document.getElementById('approvalModal');
    if (modal) {
        modal.style.display = 'none';
    }
    refreshModalScrollLock();
}

// Close action modal
function closeActionModal(reopenInvoiceModal = true) {
    const modal = document.getElementById('actionModal');
    if (modal) {
        modal.style.display = 'none';
    }

    if (reopenInvoiceModal && returnToInvoiceModalOnActionClose && currentInvoiceId) {
        openApprovalModal(currentInvoiceId);
    }

    if (!reopenInvoiceModal) {
        returnToInvoiceModalOnActionClose = false;
    }

    refreshModalScrollLock();
}

function refreshModalScrollLock() {
    const visibleModal = Array.from(document.querySelectorAll('.fv-modal-overlay')).some((modalEl) => {
        return window.getComputedStyle(modalEl).display !== 'none';
    });

    document.body.style.overflow = visibleModal ? 'hidden' : '';
}

function closeDynamicModal(trigger) {
    const overlay = trigger?.closest('.fv-modal-overlay');
    if (overlay) {
        overlay.remove();
    }
    refreshModalScrollLock();
}

function applyActionModalState(action, invoiceId = currentInvoiceId) {
    const invoice = allInvoices.find(inv => inv.id === invoiceId);
    const invoiceNumber = invoice?.invoice_number || `#${invoiceId}`;
    const reasonField = document.getElementById('reasonField');
    const rejectTypeField = document.getElementById('rejectTypeField');
    const rejectTypeSelect = document.getElementById('rejectionType');
    const confirmBtn = document.getElementById('confirmActionBtn');

    currentAction = action;

    if (action === 'approve') {
        document.getElementById('actionModalTitle').textContent = 'Approve Invoice';
        document.getElementById('actionModalMessage').innerHTML =
            `<i class="bi bi-exclamation-circle text-warning me-2"></i>Are you sure you want to approve invoice ${invoiceNumber}?`;
        if (reasonField) reasonField.style.display = 'none';
        if (rejectTypeField) rejectTypeField.style.display = 'none';
        if (confirmBtn) {
            confirmBtn.className = 'btn btn-success';
            confirmBtn.textContent = 'Approve';
        }
        return;
    }

    if (action === 'reject') {
        currentRejectCategory = 'editable';
        document.getElementById('actionModalTitle').textContent = 'Reject Invoice';
        document.getElementById('actionModalMessage').innerHTML =
            `<i class="bi bi-exclamation-circle text-warning me-2"></i>Are you sure you want to reject invoice ${invoiceNumber}?`;
        if (reasonField) reasonField.style.display = 'block';
        if (rejectTypeField) rejectTypeField.style.display = 'block';
        if (rejectTypeSelect) rejectTypeSelect.value = 'editable';
        if (confirmBtn) {
            confirmBtn.className = 'btn btn-danger';
            confirmBtn.textContent = 'Reject';
        }
    }
}

// Click outside modal to close
document.addEventListener('click', function(event) {
    const actionModal = document.getElementById('actionModal');
    if (event.target === actionModal) {
        closeActionModal();
    }
    const approvalModal = document.getElementById('approvalModal');
    if (event.target === approvalModal) {
        closeApprovalModal();
    }
});

// ===== ACTION FUNCTIONS =====
// Functions that handle approve, reject, hold, edit, acknowledge, and resend actions

// Opens confirmation modal for approving an invoice
async function approveInvoice(invoiceId) {
    if (!requireApprovalAdminPermission()) return;

    currentInvoiceId = invoiceId;
    returnToInvoiceModalOnActionClose = true;
    closeApprovalModal();
    applyActionModalState('approve', invoiceId);
    
    document.getElementById('actionModal').style.display = 'flex';
    refreshModalScrollLock();
}

async function rejectInvoice(invoiceId) {
    if (!requireApprovalAdminPermission()) return;

    currentInvoiceId = invoiceId;
    returnToInvoiceModalOnActionClose = true;
    closeApprovalModal();
    document.getElementById('rejectionReason').value = '';
    applyActionModalState('reject', invoiceId);
    
    document.getElementById('actionModal').style.display = 'flex';
    refreshModalScrollLock();
}

async function holdInvoice(invoiceId) {
    if (!requireApprovalAdminPermission()) return;

    currentAction = 'hold';
    currentInvoiceId = invoiceId;
    returnToInvoiceModalOnActionClose = true;
    closeApprovalModal();
    
    const invoice = allInvoices.find(inv => inv.id === invoiceId);
    document.getElementById('actionModalTitle').textContent = 'Put Invoice On Hold';
    document.getElementById('actionModalMessage').innerHTML = 
        `<i class="bi bi-exclamation-circle text-warning me-2"></i>Are you sure you want to put invoice ${invoice.invoice_number} on hold?`;
    document.getElementById('reasonField').style.display = 'none';
    const rejectTypeField = document.getElementById('rejectTypeField');
    if (rejectTypeField) rejectTypeField.style.display = 'none';
    document.getElementById('rejectionReason').value = '';
    document.getElementById('confirmActionBtn').className = 'btn btn-warning';
    document.getElementById('confirmActionBtn').textContent = 'Put On Hold';
    
    document.getElementById('actionModal').style.display = 'flex';
    refreshModalScrollLock();
}

async function runPendingAICheck(invoiceId) {
    if (!IS_APPROVAL_ADMIN) {
        showError('Only admin users can run AI checks on approvals.');
        return false;
    }

    const existingState = aiReviewStatusByInvoice[invoiceId];
    if (existingState && existingState.checked) {
        await openApprovalModal(invoiceId);
        return true;
    }

    const triggerBtn = document.querySelector('#modalActionButtons .btn-outline-primary.approval-action-btn');
    const originalHtml = triggerBtn ? triggerBtn.innerHTML : '';

    try {
        if (triggerBtn) {
            triggerBtn.disabled = true;
            triggerBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>Checking...';
        }

        const response = await fetch(`/api/ai/detect-rejection/${invoiceId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();
        if (!result.success || !result.analysis) {
            throw new Error(result.error || 'AI validation failed');
        }

        aiReviewStatusByInvoice[invoiceId] = {
            checked: true,
            hasIssues: !!result.analysis.should_reject,
            analysis: result.analysis,
            checkedAt: Date.now()
        };

        await openApprovalModal(invoiceId);
        return true;
    } catch (error) {
        console.error('AI pre-check failed:', error);
        showError('Unable to complete AI validation. Please try again.');
        if (triggerBtn) {
            triggerBtn.disabled = false;
            triggerBtn.innerHTML = originalHtml || '<i class="bi bi-stars"></i> Check with AI';
        }
        return false;
    }
}

async function ensureAICheckBeforeAction(invoiceId) {
    return false;
}

// Opens inline edit view for fixing rejected invoices
function editInvoice(invoiceId) {
    // Close the modal first
    closeApprovalModal();
    // Load edit form inline instead of redirecting
    showEditInvoiceView(invoiceId); // Display edit interface
}

// Loads and displays the inline edit form with pre-filled invoice data
// Fetches invoice data from backend and builds HTML form dynamically
async function showEditInvoiceView(invoiceId) {
    console.log('Loading edit form for invoice:', invoiceId);
    
    try {
        // Show loading state
        const editView = document.getElementById('editInvoiceView');
        editView.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>';
        editView.style.display = 'block';
        document.getElementById('approvalsListView').style.display = 'none';
        
        // Fetch invoice data
        const response = await fetch(`/api/invoices/${invoiceId}/edit-data`);
        console.log('Fetch response status:', response.status);
        
        if (!response.ok) {
            throw new Error('Failed to load invoice data');
        }
        
        const data = await response.json();
        console.log('Data received:', data);
        
        if (!data.success) {
            throw new Error(data.error || 'Failed to load invoice');
        }
        
        // Build the edit form HTML
        const invoice = data.invoice;
        const items = data.items;
        
        // Build form HTML string with pre-filled data
        const formHTML = `
        <div class="edit-invoice-page" style="max-width: 1200px; margin: 0 auto;">
          <!-- Header -->
          <div class="d-flex align-items-center justify-content-between mb-4">
            <div class="d-flex align-items-center gap-3">
              <button class="back-btn" onclick="returnToApprovalsView()" type="button">
                <i class="bi bi-arrow-left"></i>
              </button>
              <div>
                <h1 class="fw-bold mb-1">Re-edit Invoice</h1>
                                <p class="text-muted mb-0">Review flagged items and resubmit ${invoice.invoice_number}</p>
              </div>
            </div>
            <button class="btn btn-primary" type="button" onclick="runAIValidation()" id="aiValidationBtn" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none;">
              <i class="bi bi-stars me-2"></i>AI Validation
            </button>
          </div>

          ${data.rejection_title ? `
          <!-- Rejection Alert -->
          <div class="alert alert-danger d-flex align-items-start gap-3 mb-4">
            <i class="bi bi-exclamation-circle fs-5"></i>
            <div class="flex-grow-1">
              <div class="fw-bold mb-1">${data.rejection_title}</div>
              <div class="mb-2">${data.rejection_description}</div>
              ${data.rejection_category && data.rejection_category.suggestions ? `
                <div class="mt-2">
                  <div class="fw-semibold small mb-1">💡 AI Suggestions:</div>
                  <ul class="small mb-0">
                    ${data.rejection_category.suggestions.map(s => `<li>${s}</li>`).join('')}
                  </ul>
                </div>
              ` : ''}
            </div>
          </div>
          ` : ''}

          <form id="editInvoiceForm">
            <!-- Client Information -->
            <div class="card p-4 mb-3">
              <div class="d-flex align-items-center gap-2 mb-3">
                <i class="bi bi-building fs-5"></i>
                <h6 class="mb-0 fw-semibold">Client Information</h6>
              </div>
              
              <div class="row g-3">
                <div class="col-md-6">
                  <label class="form-label">Company Name *</label>
                  <input type="text" class="form-control" name="company_name" value="${invoice.client_name || ''}" 
                    minlength="2" maxlength="100" 
                    title="Enter company name (2-100 characters)" 
                    required>
                </div>
                <div class="col-md-6">
                  <label class="form-label">Email *</label>
                  <input type="email" class="form-control" name="email" value="${invoice.email || ''}" 
                    pattern="[^@]+@[^@]+\\.[^@]+" 
                    title="Please enter a valid email address" 
                    required>
                </div>
                <div class="col-md-6">
                  <label class="form-label">Phone (Optional)</label>
                                    <input type="hidden" name="phone_country" value="SG">
                                    <div class="input-group">
                                        <button class="btn btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-role="phone-country-toggle">+65</button>
                                        <ul class="dropdown-menu p-2" data-role="phone-country-menu" style="min-width: 340px;"></ul>
                                        <input type="tel" class="form-control" name="phone_number" value="" inputmode="numeric" placeholder="Digits only">
                                    </div>
                                    <small class="text-muted">Choose country from dropdown. Number accepts digits only.</small>
                </div>
              </div>
            </div>

            <!-- Invoice Details -->
            <div class="card p-4 mb-3">
              <div class="d-flex align-items-center gap-2 mb-3">
                <i class="bi bi-file-earmark-text fs-5"></i>
                <h6 class="mb-0 fw-semibold">Invoice Details</h6>
              </div>
              
              <div class="row g-3">
                <div class="col-md-6">
                  <label class="form-label">Invoice Number</label>
                  <input type="text" class="form-control" name="invoice_number" value="${invoice.invoice_number}" readonly style="background: #f8fafc;">
                </div>
                <div class="col-md-6">
                  <label class="form-label">Payment Terms *</label>
                                    <select class="form-select" name="payment_terms" onchange="updateDueDateInline()" required>
                    <option value="Net 15" ${invoice.payment_terms === 'Net 15' ? 'selected' : ''}>Net 15</option>
                    <option value="Net 30" ${invoice.payment_terms === 'Net 30' ? 'selected' : ''}>Net 30</option>
                    <option value="Net 45" ${invoice.payment_terms === 'Net 45' ? 'selected' : ''}>Net 45</option>
                    <option value="Net 60" ${invoice.payment_terms === 'Net 60' ? 'selected' : ''}>Net 60</option>
                    <option value="Due on Receipt" ${invoice.payment_terms === 'Due on Receipt' ? 'selected' : ''}>Due on Receipt</option>
                  </select>
                </div>
                <div class="col-md-6">
                  <label class="form-label">Invoice Date *</label>
                  <input type="date" class="form-control" name="invoice_date" value="${invoice.invoice_date}" 
                    onchange="updateDueDateInline()"
                    required>
                </div>
                <div class="col-md-6">
                  <label class="form-label">Due Date *</label>
                  <input type="date" class="form-control" name="due_date" value="${invoice.due_date}" 
                    min="${invoice.invoice_date}" 
                                        readonly style="background: #f8fafc;"
                    title="Due date must be after invoice date" 
                    required>
                </div>
              </div>
            </div>

            <!-- Line Items -->
            <div class="card p-4 mb-3">
              <div class="d-flex align-items-center justify-content-between mb-3">
                <div class="d-flex align-items-center gap-2">
                  <i class="bi bi-list-ul fs-5"></i>
                  <h6 class="mb-0 fw-semibold">Line Items</h6>
                </div>
                <button type="button" class="btn btn-sm btn-outline-primary" onclick="addLineItemInline()">
                  <i class="bi bi-plus-lg"></i> Add Item
                </button>
              </div>
              
              <div class="table-responsive">
                <table class="table" id="lineItemsTableInline">
                  <thead>
                    <tr>
                      <th style="width: 40%;">Description</th>
                      <th style="width: 15%;">Quantity</th>
                      <th style="width: 20%;">Rate (S$)</th>
                      <th style="width: 20%;">Amount (S$)</th>
                      <th style="width: 5%;"></th>
                    </tr>
                  </thead>
                  <tbody id="lineItemsBodyInline">
                    ${items.map(item => `
                    <tr>
                      <td><input type="text" class="form-control" name="description[]" value="${item.description}" 
                        minlength="3" maxlength="200" 
                        title="Enter a description (3-200 characters)" 
                        required></td>
                      <td><input type="number" class="form-control" name="quantity[]" value="${item.quantity}" 
                        min="1" max="9999" 
                        title="Quantity must be at least 1" 
                        required oninput="calculateRowInline(this)"></td>
                      <td><input type="number" class="form-control" name="rate[]" value="${item.rate}" 
                        min="0" max="999999" step="10" 
                        title="Enter rate (in multiples of $10)" 
                        required oninput="calculateRowInline(this)"></td>
                      <td><input type="number" class="form-control" name="amount[]" value="${item.amount}" readonly style="background: #f8fafc;"></td>
                      <td>
                        <button type="button" class="btn btn-sm btn-link text-danger" onclick="deleteRowInline(this)">
                          <i class="bi bi-trash"></i>
                        </button>
                      </td>
                    </tr>
                    `).join('')}
                  </tbody>
                </table>
              </div>

              <!-- Totals -->
              <div class="d-flex justify-content-end mt-3">
                <div style="min-width: 350px;">
                  <div class="d-flex justify-content-between py-2 border-bottom">
                    <span>Subtotal:</span>
                    <span class="fw-semibold" id="subtotalDisplayInline">$0.00</span>
                  </div>
                  <div class="d-flex justify-content-between py-2 border-bottom">
                    <span>GST (9%):</span>
                    <span class="fw-semibold" id="gstDisplayInline">$0.00</span>
                  </div>
                  <div class="d-flex justify-content-between py-2 bg-light px-3 rounded mt-2">
                    <span class="fw-bold">Total:</span>
                    <span class="fw-bold text-primary" id="totalDisplayInline">$0.00</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Notes -->
            <div class="card p-4 mb-3">
              <div class="d-flex align-items-center gap-2 mb-3">
                <i class="bi bi-file-text fs-5"></i>
                <h6 class="mb-0 fw-semibold">Notes / Additional Information</h6>
              </div>
              <textarea class="form-control" name="notes" rows="3" 
                maxlength="1000" 
                placeholder="Enter any additional notes or information... (max 1000 characters)">${invoice.notes || ''}</textarea>
            </div>

            <!-- Action Buttons -->
            <div class="d-flex justify-content-end gap-3 mb-4">
              <button type="button" class="btn btn-outline-secondary px-4" onclick="returnToApprovalsView()">
                Cancel
              </button>
              <button type="submit" class="btn btn-primary px-4">
                <i class="bi bi-check-circle me-2"></i>
                Resubmit for Approval
              </button>
            </div>
          </form>
        </div>
        `;
        
        // Show the form
        editView.innerHTML = formHTML;
        
        // Initialize calculations
        setTimeout(() => {
            updateDueDateInline();
            calculateTotalsInline();

            inlinePhoneController = setupInternationalPhoneInputs({
                countryToggleSelector: '[data-role="phone-country-toggle"]',
                countryMenuSelector: '[data-role="phone-country-menu"]',
                countryIsoSelector: 'input[name="phone_country"]',
                phoneNumberSelector: 'input[name="phone_number"]',
                defaultIso: 'SG',
                initialPhone: invoice.phone || ''
            });
        }, 100);
        
        // Setup form submit handler
        document.getElementById('editInvoiceForm').onsubmit = async function(e) {
            e.preventDefault();
            await submitEditInline(invoiceId, this);
        };
        
    } catch (error) {
        console.error('Error loading edit form:', error);
        showError('Failed to load edit form. Please try again.');
        returnToApprovalsView();
    }
}

// Returns from edit view back to approvals list view
// Hides the edit form and refreshes the approvals data
function returnToApprovalsView() {
    // Hide edit view
    document.getElementById('editInvoiceView').style.display = 'none';
    
    // Show approvals list view
    document.getElementById('approvalsListView').style.display = 'block';
    
    // Reload approvals data to reflect any changes
    loadApprovals();
}

// ===== INLINE EDIT FORM HELPER FUNCTIONS =====
// Functions for managing the inline edit form's line items and calculations

// Recalculates the amount for a single line item row
// Multiplies quantity by rate and updates the amount field
function calculateRowInline(input) {
    const row = input.closest('tr');
    const qty = parseFloat(row.querySelector('input[name="quantity[]"]').value) || 0;
    const rate = parseFloat(row.querySelector('input[name="rate[]"]').value) || 0;
    const amount = qty * rate;
    row.querySelector('input[name="amount[]"]').value = amount.toFixed(2);
    calculateTotalsInline();
}

// Recalculates subtotal, GST, and total for all line items
// Updates the totals display at the bottom of the line items table
function calculateTotalsInline() {
    let subtotal = 0; // Initialize subtotal
    const amountInputs = document.querySelectorAll('input[name="amount[]"]');
    amountInputs.forEach(input => {
        subtotal += parseFloat(input.value) || 0; // Sum all line item amounts
    });
    
    const gst = subtotal * 0.09; // Calculate 9% GST
    const total = subtotal + gst; // Calculate final total
    
    const subtotalDisplay = document.getElementById('subtotalDisplayInline');
    const gstDisplay = document.getElementById('gstDisplayInline');
    const totalDisplay = document.getElementById('totalDisplayInline');
    
    if (subtotalDisplay) subtotalDisplay.textContent = '$' + subtotal.toFixed(2);
    if (gstDisplay) gstDisplay.textContent = '$' + gst.toFixed(2);
    if (totalDisplay) totalDisplay.textContent = '$' + total.toFixed(2);
}

// Updates the due date when invoice date changes
// Automatically sets due date based on selected payment terms
function updateDueDateInline() {
    const invoiceDateInput = document.querySelector('input[name="invoice_date"]');
    const dueDateInput = document.querySelector('input[name="due_date"]');
    const paymentTermsSelect = document.querySelector('select[name="payment_terms"]');
    
    if (invoiceDateInput && dueDateInput && paymentTermsSelect && invoiceDateInput.value) {
        const paymentTerms = paymentTermsSelect.value || 'Net 30';
        const daysByTerms = {
            'Net 15': 15,
            'Net 30': 30,
            'Net 45': 45,
            'Net 60': 60,
            'Due on Receipt': 0
        };
        const daysToAdd = daysByTerms[paymentTerms] ?? 30;

        const invoiceDate = new Date(invoiceDateInput.value);
        const dueDate = new Date(invoiceDate);
        dueDate.setDate(dueDate.getDate() + daysToAdd);
        
        // Format date as YYYY-MM-DD for input
        const year = dueDate.getFullYear();
        const month = String(dueDate.getMonth() + 1).padStart(2, '0');
        const day = String(dueDate.getDate()).padStart(2, '0');
        
        dueDateInput.value = `${year}-${month}-${day}`;
        dueDateInput.min = invoiceDateInput.value; // Update min constraint
    }
}

// Adds a new blank line item row to the edit form
// Allows users to add additional items when editing an invoice
function addLineItemInline() {
    const tbody = document.getElementById('lineItemsBodyInline');
    const newRow = document.createElement('tr'); // Create new table row
    newRow.innerHTML = `
        <td><input type="text" class="form-control" name="description[]" required></td>
        <td><input type="number" class="form-control" name="quantity[]" value="1" min="1" required oninput="calculateRowInline(this)"></td>
        <td><input type="number" class="form-control" name="rate[]" value="0" min="0" step="0.01" required oninput="calculateRowInline(this)"></td>
        <td><input type="number" class="form-control" name="amount[]" value="0.00" readonly style="background: #f8fafc;"></td>
        <td>
            <button type="button" class="btn btn-sm btn-link text-danger" onclick="deleteRowInline(this)">
                <i class="bi bi-trash"></i>
            </button>
        </td>
    `;
    tbody.appendChild(newRow);
}

// Deletes a line item row from the edit form
// Prevents deletion if it's the last remaining row
function deleteRowInline(btn) {
    const row = btn.closest('tr'); // Find the row containing the delete button
    const tbody = document.getElementById('lineItemsBodyInline');
    if (tbody.children.length > 1) {
        row.remove(); // Remove the row
        calculateTotalsInline(); // Recalculate totals
    } else {
        showError('You must have at least one line item'); // Prevent deletion of last row
    }
}

// Submits the edited invoice data back to the server
// Collects all form data, formats it, and sends it via POST request
async function submitEditInline(invoiceId, form) {
    const formData = new FormData(form); // Extract form data
    
    // Validate email format before submission
    const email = formData.get('email');
    const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
    if (email && !emailPattern.test(email)) {
        showError('Please enter a valid email address');
        return; // Stop submission
    }

    if (inlinePhoneController) {
        const phoneValidation = inlinePhoneController.validate();
        if (!phoneValidation.valid) {
            showError(phoneValidation.message);
            return;
        }
    }

    const phonePayload = inlinePhoneController
        ? inlinePhoneController.getPayload()
        : { phone: '', phone_country: 'SG', phone_number: '' };
    
    const data = {
        // Build invoice data object
        company_name: formData.get('company_name'),
        email: email,
        phone: phonePayload.phone,
        phone_country: phonePayload.phone_country,
        phone_number: phonePayload.phone_number,
        invoice_number: formData.get('invoice_number'),
        payment_terms: formData.get('payment_terms'),
        invoice_date: formData.get('invoice_date'),
        due_date: formData.get('due_date'),
        notes: formData.get('notes'),
        items: [] // Will be populated with line items below
    };
    
    // Collect line items
    const descriptions = formData.getAll('description[]');
    const quantities = formData.getAll('quantity[]');
    const rates = formData.getAll('rate[]');
    
    for (let i = 0; i < descriptions.length; i++) {
        data.items.push({
            description: descriptions[i],
            quantity: parseFloat(quantities[i]),
            rate: parseFloat(rates[i]),
            amount: parseFloat(quantities[i]) * parseFloat(rates[i])
        });
    }
    
    try {
        const response = await fetch(`/api/invoices/${invoiceId}/resubmit`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showSuccess('Invoice resubmitted successfully!');
            returnToApprovalsView();
        } else {
            // Show specific error message from backend
            showError(result.error || 'Failed to resubmit invoice');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Failed to resubmit invoice. Please try again.');
    }
}

// Opens confirmation modal for acknowledging a rejected invoice
// Acknowledgment places the invoice on hold until external issues are resolved
function acknowledgeInvoice(invoiceId) {
    if (!canRunApprovalAction('acknowledge')) {
        showError('Employees can only acknowledge rejected invoices or resend on-hold invoices.');
        return;
    }

    currentAction = 'acknowledge'; // Set action type
    currentInvoiceId = invoiceId; // Store invoice ID
    returnToInvoiceModalOnActionClose = true;
    closeApprovalModal();
    
    const invoice = allInvoices.find(inv => inv.id === invoiceId);
    document.getElementById('actionModalTitle').textContent = 'Acknowledge Rejected Invoice';
    document.getElementById('actionModalMessage').innerHTML = 
        `<i class="bi bi-exclamation-circle text-warning me-2"></i>Acknowledge invoice ${invoice.invoice_number}? This will place it on hold until the issue is resolved.`;
    document.getElementById('reasonField').style.display = 'none';
    const rejectTypeField = document.getElementById('rejectTypeField');
    if (rejectTypeField) rejectTypeField.style.display = 'none';
    document.getElementById('confirmActionBtn').className = 'btn btn-warning';
    document.getElementById('confirmActionBtn').textContent = 'Acknowledge & Place On Hold';
    
    document.getElementById('actionModal').style.display = 'flex';
    refreshModalScrollLock();
}

// Opens confirmation modal for resending an on-hold invoice for approval
// Changes the status from 'on-hold' back to 'pending'
function resendInvoice(invoiceId) {
    if (!canRunApprovalAction('resend')) {
        showError('Employees can only acknowledge rejected invoices or resend on-hold invoices.');
        return;
    }

    currentAction = 'resend'; // Set action type
    currentInvoiceId = invoiceId; // Store invoice ID
    returnToInvoiceModalOnActionClose = true;
    closeApprovalModal();
    
    const invoice = allInvoices.find(inv => inv.id === invoiceId);
    document.getElementById('actionModalTitle').textContent = 'Resend for Approval';
    document.getElementById('actionModalMessage').innerHTML = 
        `<i class="bi bi-exclamation-circle text-warning me-2"></i>Resubmit invoice ${invoice.invoice_number} for approval? This will change the status to pending.`;
    document.getElementById('reasonField').style.display = 'none';
    const rejectTypeField = document.getElementById('rejectTypeField');
    if (rejectTypeField) rejectTypeField.style.display = 'none';
    document.getElementById('confirmActionBtn').className = 'btn btn-primary';
    document.getElementById('confirmActionBtn').textContent = 'Resend for Approval';
    
    document.getElementById('actionModal').style.display = 'flex';
    refreshModalScrollLock();
}

// Event listener for resend buttons using data attributes (like invoice_delivery)
// Alternative click handler for resend buttons that use data-invoice-id attribute
document.addEventListener('click', function(event) {
    if (event.target.classList.contains('btn-resend-pill')) {
        const invoiceId = parseInt(event.target.dataset.invoiceId); // Get invoice ID from data attribute
        if (invoiceId) {
            resendInvoice(invoiceId); // Trigger resend action
        }
    }
});

function viewInvoice(invoiceId) {
    // Redirect to invoice detail view
    window.location.href = `/invoices/${invoiceId}`;
}

// Confirm action button handler
// Handles the final confirmation when user confirms an action in the modal
document.addEventListener('DOMContentLoaded', function() {
    const confirmBtn = document.getElementById('confirmActionBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', async function() {
            if (!canRunApprovalAction(currentAction)) {
                showError('Employees can only acknowledge rejected invoices or resend on-hold invoices.');
                return;
            }

            let reason = document.getElementById('rejectionReason').value; // Get reason if provided
            const rejectTypeSelect = document.getElementById('rejectionType');
            if (rejectTypeSelect) {
                currentRejectCategory = rejectTypeSelect.value || 'editable';
            }

            // For reject action, auto-generate AI reasoning when manual reason is empty
            if (currentAction === 'reject' && (!reason || !reason.trim())) {
                try {
                    const aiResponse = await fetch(`/api/ai/detect-rejection/${currentInvoiceId}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    });
                    const aiResult = await aiResponse.json();
                    if (aiResult.success && aiResult.analysis) {
                        const analysis = aiResult.analysis;
                        if (analysis.should_reject) {
                            const title = analysis.rejection_title || 'AI Rejection Reason';
                            const description = analysis.rejection_description || 'Detected invoice issues requiring correction.';
                            reason = `${title}: ${description}`;
                            currentRejectCategory = rejectTypeSelect?.value || 'editable';
                        } else {
                            reason = 'No invoice-data issues detected by AI; this may be a business or external issue requiring acknowledgement.';
                            currentRejectCategory = 'non-editable';
                            if (rejectTypeSelect) rejectTypeSelect.value = 'non-editable';
                        }
                    }
                } catch (aiError) {
                    console.error('AI auto-reason generation failed:', aiError);
                }
            }

            if (currentAction === 'reject' && (!reason || !reason.trim())) {
                showError('Enter a specific rejection reason before continuing.');
                return;
            }

            if (currentAction === 'reject') {
                const suffix = currentRejectCategory === 'editable' ? ' | editable' : ' | non-editable';
                if (!reason.includes(' | editable') && !reason.includes(' | non-editable')) {
                    reason = `${reason}${suffix}`;
                }
            }
            
            try {
                // Send action request to backend
                const response = await fetch('/api/approvals/action', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        invoice_id: currentInvoiceId, // Invoice to act on
                        action: currentAction, // Action type (approve, reject, hold, etc.)
                        reason: reason || null // Optional reason for reject/hold
                    })
                });
                
                if (!response.ok) {
                    const errorPayload = await response.json().catch(() => ({}));
                    throw new Error(errorPayload.error || 'Action failed');
                }
                
                const result = await response.json();
                
                // Close modal
                closeActionModal(false);
                closeApprovalModal();
                
                // Show success message with custom text based on action
                let successMessage = result.message || 'Action completed successfully';
                if (currentAction === 'acknowledge') {
                    // Custom message for acknowledge action
                    successMessage = 'Invoice acknowledged and placed on hold. You can resend once the client issue is resolved.';
                } else if (currentAction === 'resend') {
                    // Custom message for resend action
                    successMessage = 'Invoice resubmitted for approval!';
                }
                showSuccess(successMessage); // Display success notification
                
                // Reload data to reflect changes
                await loadApprovals();
                
            } catch (error) {
                console.error('Error performing action:', error);
                showError(error.message || 'Failed to perform action. Please try again.');
            }
        });
    }
});

// ===== UTILITY FUNCTIONS =====
// Helper functions for showing notifications and formatting data

function getToastStackContainer() {
    let container = document.getElementById('fvToastStack');
    if (!container) {
        container = document.createElement('div');
        container.id = 'fvToastStack';
        container.className = 'fv-toast-stack';
        document.body.appendChild(container);
    }
    return container;
}

function enqueueToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `fv-toast fv-toast-${type}`;
    toast.innerHTML = type === 'success'
        ? `
            <i class="bi bi-check-circle-fill"></i>
            <span>${message}</span>
        `
        : `
            <i class="bi bi-exclamation-triangle-fill"></i>
            <span>${message}</span>
        `;

    const stack = getToastStackContainer();
    stack.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Displays a success toast notification
function showSuccess(message) {
    enqueueToast(message, 'success');
}

// Displays an error toast notification
function showError(message) {
    enqueueToast(message, 'error');
}

// ===== AI VALIDATION FUNCTION =====
// AI-powered invoice validation to detect issues and provide suggestions

async function runAIValidation() {
    const btn = document.getElementById('aiValidationBtn');
    const originalHTML = btn.innerHTML;
    
    try {
        // Show loading state
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Analyzing...';
        
        // Collect form data
        const form = document.getElementById('editInvoiceForm');
        const formData = new FormData(form);

        if (inlinePhoneController) {
            const phoneValidation = inlinePhoneController.validate();
            if (!phoneValidation.valid) {
                throw new Error(phoneValidation.message);
            }
        }

        const phonePayload = inlinePhoneController
            ? inlinePhoneController.getPayload()
            : { phone: '', phone_country: 'SG', phone_number: '' };
        
        const invoiceData = {
            invoice_number: formData.get('invoice_number'),
            company_name: formData.get('company_name'),
            email: formData.get('email'),
            phone: phonePayload.phone,
            phone_country: phonePayload.phone_country,
            phone_number: phonePayload.phone_number,
            payment_terms: formData.get('payment_terms'),
            invoice_date: formData.get('invoice_date'),
            due_date: formData.get('due_date'),
            notes: formData.get('notes'),
            items: []
        };
        
        // Collect line items
        const descriptions = formData.getAll('description[]');
        const quantities = formData.getAll('quantity[]');
        const rates = formData.getAll('rate[]');
        
        for (let i = 0; i < descriptions.length; i++) {
            const quantity = parseInt(quantities[i]) || 0;
            const rate = parseFloat(rates[i]) || 0;
            const amount = quantity * rate;
            invoiceData.items.push({
                description: descriptions[i],
                quantity: quantity,
                rate: rate,
                amount: amount
            });
        }
        
        // Call AI validation API
        const response = await fetch('/api/ai/validate-invoice', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(invoiceData)
        });
        
        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.error || 'Validation failed');
        }
        
        const validation = result.validation;
        
        // Display validation results in a modal
        displayValidationResults(validation);
        
    } catch (error) {
        console.error('AI validation error:', error);
        showError(error.message || 'AI validation failed. Please check your data and try again.');
    } finally {
        // Restore button state
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

function displayValidationResults(validation) {
    // Create modal overlay
    const modal = document.createElement('div');
    modal.className = 'fv-modal-overlay';
    modal.style.display = 'flex';
    
    // Determine color scheme based on score
    let scoreColor = '#10b981'; // green
    let scoreLabel = 'Excellent';
    if (validation.score < 50) {
        scoreColor = '#ef4444'; // red
        scoreLabel = 'Needs Improvement';
    } else if (validation.score < 80) {
        scoreColor = '#f59e0b'; // orange
        scoreLabel = 'Good';
    }
    
    const severityRank = { high: 0, medium: 1, low: 2 };

    const rawIssues = Array.isArray(validation.issues)
        ? validation.issues.map((issue) => {
            if (typeof issue === 'string') {
                return { message: issue, severity: 'medium' };
            }
            return {
                message: issue?.message || String(issue || ''),
                severity: String(issue?.severity || 'medium').toLowerCase()
            };
        }).filter(issue => issue.message && issue.message.trim())
        : [];

    const normalizeIssueKey = (message) => String(message || '')
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();

    const issueByMessage = new Map();
    rawIssues.forEach(issue => {
        const key = normalizeIssueKey(issue.message);
        const existing = issueByMessage.get(key);
        if (!existing || severityRank[issue.severity] < severityRank[existing.severity]) {
            issueByMessage.set(key, issue);
        }
    });
    const issues = Array.from(issueByMessage.values()).sort((a, b) => {
        const rankDiff = (severityRank[a.severity] ?? 1) - (severityRank[b.severity] ?? 1);
        if (rankDiff !== 0) return rankDiff;
        return a.message.localeCompare(b.message);
    });

    const suggestions = Array.isArray(validation.suggestions)
        ? validation.suggestions.filter(s => String(s || '').trim())
        : [];

    // Group issues by severity
    const highIssues = issues.filter(i => i.severity === 'high');
    const mediumIssues = issues.filter(i => i.severity === 'medium');
    const lowIssues = issues.filter(i => i.severity === 'low');
    const hasIssues = issues.length > 0;
    const hasSuggestions = suggestions.length > 0;
    
    modal.innerHTML = `
        <div class="fv-modal" style="max-width: 650px;">
            <div class="fv-modal-header">
                <div>
                    <h5 class="mb-0 fw-bold">
                        <i class="bi bi-stars me-2"></i>AI Validation Results
                    </h5>
                    ${validation.ai_enabled ? 
                        '<small class="text-muted">Powered by AI</small>' : 
                        '<small class="text-warning"><i class="bi bi-exclamation-triangle"></i> Using rule-based validation (AI not configured)</small>'}
                </div>
                <button class="fv-modal-close" onclick="closeDynamicModal(this)">×</button>
            </div>
            
            <div class="fv-modal-body">
                <!-- Score Display -->
                <div class="text-center py-3 mb-4" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; color: white;">
                    <div style="font-size: 3rem; font-weight: bold;">${validation.score}</div>
                    <div style="font-size: 1.2rem; opacity: 0.9;">${scoreLabel}</div>
                    <small class="text-muted d-block mt-1" style="font-size: 0.8rem;">Quality Score (0-100)</small>
                    <div style="font-size: 0.9rem; opacity: 0.8; margin-top: 0.5rem;">
                        ${validation.valid ? '✓ Ready to submit' : '⚠ Fix issues before submitting'}
                    </div>
                </div>
                
                ${hasIssues ? `
                    <div class="mb-4">
                        <h6 class="fw-bold mb-3">Issues Found (${issues.length})</h6>
                        
                        ${highIssues.length > 0 ? `
                            <div class="mb-3">
                                <div class="fw-semibold text-danger mb-2">
                                    <i class="bi bi-exclamation-circle-fill me-1"></i>High Priority (${highIssues.length})
                                </div>
                                <ul class="small">
                                    ${highIssues.map(issue => `<li>${issue.message}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                        
                        ${mediumIssues.length > 0 ? `
                            <div class="mb-3">
                                <div class="fw-semibold text-warning mb-2">
                                    <i class="bi bi-exclamation-triangle-fill me-1"></i>Medium Priority (${mediumIssues.length})
                                </div>
                                <ul class="small">
                                    ${mediumIssues.map(issue => `<li>${issue.message}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                        
                        ${lowIssues.length > 0 ? `
                            <div class="mb-3">
                                <div class="fw-semibold text-info mb-2">
                                    <i class="bi bi-info-circle-fill me-1"></i>Low Priority (${lowIssues.length})
                                </div>
                                <ul class="small">
                                    ${lowIssues.map(issue => `<li>${issue.message}</li>`).join('')}
                                </ul>
                            </div>
                        ` : ''}
                    </div>
                ` : (hasSuggestions
                    ? '<div class="alert alert-info"><i class="bi bi-info-circle-fill me-2"></i>No blocking issues detected. Review suggestions below.</div>'
                    : '<div class="alert alert-success"><i class="bi bi-check-circle-fill me-2"></i>No issues detected!</div>')}
                
                ${hasSuggestions ? `
                    <div class="mb-3">
                        <h6 class="fw-bold mb-2"><i class="bi bi-lightbulb me-1"></i>Suggestions</h6>
                        <ul class="small">
                            ${suggestions.map(s => `<li>${s}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
            </div>
            
            <div class="fv-modal-footer">
                <button class="btn btn-outline-secondary" onclick="closeDynamicModal(this)">Review Issues</button>
                ${validation.valid ? 
                    '<button class="btn btn-primary" onclick="closeDynamicModal(this); document.getElementById(\'editInvoiceForm\').dispatchEvent(new Event(\'submit\', { bubbles: true, cancelable: true }));">Submit Invoice</button>' : 
                    ''}
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    refreshModalScrollLock();
}

// ===== AI REJECTION DETECTION =====
// AI-powered detection of rejection reasons for invoices

async function detectWithAI() {
    if (!IS_APPROVAL_ADMIN) {
        showError('Only admin users can run AI checks on approvals.');
        return;
    }

    if (!currentInvoiceId) {
        showError('No invoice selected');
        return;
    }
    
    const btn = document.getElementById('aiDetectBtn');
    const reasonField = document.getElementById('rejectionReason');
    const originalHTML = btn.innerHTML;
    
    try {
        // Show loading state
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Analyzing...';
        
        // Call AI detection API
        const response = await fetch(`/api/ai/detect-rejection/${currentInvoiceId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            const analysis = result.analysis;
            const rejectTypeSelect = document.getElementById('rejectionType');
            
            if (analysis.should_reject) {
                applyActionModalState('reject', currentInvoiceId);
                // Format the rejection reason
                const aiTitle = (analysis.rejection_title || 'Issue').trim();
                const oneSentenceDescription = String(analysis.rejection_description || 'Detected invoice issues requiring correction.')
                    .replace(/\s+/g, ' ')
                    .split(/(?<=[.!?])\s+/)[0]
                    .trim();
                let rejectionText = `${aiTitle}: ${oneSentenceDescription}`;
                
                reasonField.value = rejectionText;
                if (rejectTypeSelect) rejectTypeSelect.value = 'editable';
                
                // Show success notification
                showSuccess('AI detected issues. Action auto-set to Reject.');
            } else {
                applyActionModalState('approve', currentInvoiceId);
                // No rejection recommended
                showSuccess('AI found no invoice-data issues. Action auto-set to Approve.');
                reasonField.value = 'No invoice-data issues detected by AI; this may be a business or external issue requiring acknowledgement.';
                if (rejectTypeSelect) rejectTypeSelect.value = 'non-editable';
            }
        } else {
            showError('AI analysis failed: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error in AI detection:', error);
        showError('Failed to run AI analysis. Please try again.');
    } finally {
        // Reset button
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

// Debounce function to reduce function calls during rapid input changes
// Helpful for search input to avoid excessive filtering
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func.apply(this, args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function handlePendingActionSelection(invoiceId, selectedAction) {
    if (!IS_APPROVAL_ADMIN) return;

    const continueBtn = document.getElementById('pendingActionContinueBtn');
    if (!continueBtn) return;

    if (!selectedAction) {
        continueBtn.disabled = true;
        continueBtn.dataset.action = '';
        return;
    }

    continueBtn.disabled = false;
    continueBtn.dataset.action = selectedAction;
}

function submitPendingActionSelection(invoiceId) {
    if (!IS_APPROVAL_ADMIN) return;

    const continueBtn = document.getElementById('pendingActionContinueBtn');
    const actionSelect = document.getElementById('pendingActionSelect');
    const selectedAction = continueBtn?.dataset.action || actionSelect?.value || '';

    if (!selectedAction) return;

    if (selectedAction === 'approve') {
        approveInvoice(invoiceId);
    } else if (selectedAction === 'reject') {
        rejectInvoice(invoiceId);
    } else if (selectedAction === 'hold') {
        holdInvoice(invoiceId);
    }

    if (actionSelect) actionSelect.value = '';
    if (continueBtn) {
        continueBtn.disabled = true;
        continueBtn.dataset.action = '';
    }
}