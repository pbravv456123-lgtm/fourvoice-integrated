// ===== GLOBAL UTILITIES =====
// Standard date formatting function used across the application

/**
 * Format date for consistent display
 * Converts various date formats to readable DD/MM/YYYY format
 * Handles null, undefined, and 'N/A' gracefully
 * @param {string|Date|null|undefined} dateValue - Date to format
 * @returns {string} Formatted date (DD/MM/YYYY) or '-'
 */
function formatDate(dateValue) {
  if (!dateValue || dateValue === 'N/A' || dateValue === 'null' || dateValue === 'None') {
    return '-';
  }
  
  try {
    const date = new Date(dateValue);
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return '-';
    }
    
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    
    return `${day}/${month}/${year}`;
  } catch (e) {
    return '-';
  }
}

/**
 * Format date and time for display
 * Converts to "DD/MM/YYYY HH:MM AM/PM" format
 * @param {string|Date|null|undefined} dateValue - Date to format
 * @returns {string} Formatted date-time or '-'
 */
function formatDateTime(dateValue) {
  if (!dateValue || dateValue === 'N/A' || dateValue === 'null' || dateValue === 'None') {
    return '-';
  }
  
  try {
    const date = new Date(dateValue);
    if (isNaN(date.getTime())) {
      return '-';
    }
    
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    
    const formattedDate = `${day}/${month}/${year}`;
    
    const formattedTime = date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    });
    
    return `${formattedDate} ${formattedTime}`;
  } catch (e) {
    return '-';
  }
}

const PHONE_COUNTRIES = [
  { iso: 'SG', name: 'Singapore', dialCode: '65', validLengths: [8], startsWith: ['6', '8', '9'] },
  { iso: 'MY', name: 'Malaysia', dialCode: '60', validLengths: [9, 10] },
  { iso: 'ID', name: 'Indonesia', dialCode: '62', validLengths: [9, 10, 11, 12] },
  { iso: 'TH', name: 'Thailand', dialCode: '66', validLengths: [8, 9] },
  { iso: 'PH', name: 'Philippines', dialCode: '63', validLengths: [10] },
  { iso: 'VN', name: 'Vietnam', dialCode: '84', validLengths: [9, 10] },
  { iso: 'CN', name: 'China', dialCode: '86', validLengths: [11] },
  { iso: 'HK', name: 'Hong Kong', dialCode: '852', validLengths: [8] },
  { iso: 'TW', name: 'Taiwan', dialCode: '886', validLengths: [9] },
  { iso: 'JP', name: 'Japan', dialCode: '81', validLengths: [10] },
  { iso: 'KR', name: 'South Korea', dialCode: '82', validLengths: [9, 10] },
  { iso: 'IN', name: 'India', dialCode: '91', validLengths: [10] },
  { iso: 'PK', name: 'Pakistan', dialCode: '92', validLengths: [10] },
  { iso: 'AE', name: 'United Arab Emirates', dialCode: '971', validLengths: [9] },
  { iso: 'SA', name: 'Saudi Arabia', dialCode: '966', validLengths: [9] },
  { iso: 'TR', name: 'Turkey', dialCode: '90', validLengths: [10] },
  { iso: 'RU', name: 'Russia', dialCode: '7', validLengths: [10] },
  { iso: 'GB', name: 'United Kingdom', dialCode: '44', validLengths: [10] },
  { iso: 'IE', name: 'Ireland', dialCode: '353', validLengths: [9] },
  { iso: 'FR', name: 'France', dialCode: '33', validLengths: [9] },
  { iso: 'DE', name: 'Germany', dialCode: '49', validLengths: [10, 11] },
  { iso: 'ES', name: 'Spain', dialCode: '34', validLengths: [9] },
  { iso: 'IT', name: 'Italy', dialCode: '39', validLengths: [9, 10] },
  { iso: 'NL', name: 'Netherlands', dialCode: '31', validLengths: [9] },
  { iso: 'BE', name: 'Belgium', dialCode: '32', validLengths: [9] },
  { iso: 'CH', name: 'Switzerland', dialCode: '41', validLengths: [9] },
  { iso: 'SE', name: 'Sweden', dialCode: '46', validLengths: [9] },
  { iso: 'NO', name: 'Norway', dialCode: '47', validLengths: [8] },
  { iso: 'DK', name: 'Denmark', dialCode: '45', validLengths: [8] },
  { iso: 'FI', name: 'Finland', dialCode: '358', validLengths: [9, 10] },
  { iso: 'PL', name: 'Poland', dialCode: '48', validLengths: [9] },
  { iso: 'PT', name: 'Portugal', dialCode: '351', validLengths: [9] },
  { iso: 'AU', name: 'Australia', dialCode: '61', validLengths: [9] },
  { iso: 'NZ', name: 'New Zealand', dialCode: '64', validLengths: [8, 9] },
  { iso: 'US', name: 'United States', dialCode: '1', validLengths: [10] },
  { iso: 'CA', name: 'Canada', dialCode: '1', validLengths: [10] },
  { iso: 'MX', name: 'Mexico', dialCode: '52', validLengths: [10] },
  { iso: 'BR', name: 'Brazil', dialCode: '55', validLengths: [10, 11] },
  { iso: 'AR', name: 'Argentina', dialCode: '54', validLengths: [10] },
  { iso: 'CL', name: 'Chile', dialCode: '56', validLengths: [9] },
  { iso: 'ZA', name: 'South Africa', dialCode: '27', validLengths: [9] },
  { iso: 'EG', name: 'Egypt', dialCode: '20', validLengths: [10] },
  { iso: 'NG', name: 'Nigeria', dialCode: '234', validLengths: [10] }
];

function getPhoneCountryByIso(iso) {
  return PHONE_COUNTRIES.find(c => c.iso === String(iso || '').toUpperCase()) || null;
}

function getPhoneCountryByDialCode(dialCode) {
  const digits = String(dialCode || '').replace(/\D/g, '');
  return PHONE_COUNTRIES.find(c => c.dialCode === digits) || null;
}

function normalizePhoneDigits(value) {
  return String(value || '').replace(/\D/g, '');
}

function getCountryFlagImageHtml(isoCode, countryName) {
  const clean = String(isoCode || '').toLowerCase();
  if (!/^[a-z]{2}$/.test(clean)) {
    return '<span class="me-2">🌐</span>';
  }
  const name = String(countryName || '').replace(/"/g, '&quot;');
  return `<img src="https://flagcdn.com/20x15/${clean}.png" alt="${name}" width="20" height="15" class="me-2" style="object-fit: cover; border-radius: 2px;">`;
}

function resolvePhoneCountryFromSelection(selection) {
  const raw = String(selection || '').trim();
  if (!raw) return null;

  const isoMatch = getPhoneCountryByIso(raw);
  if (isoMatch) return isoMatch;

  const parenMatch = raw.match(/\(\+\s*(\d{1,4})\)/);
  if (parenMatch) {
    const byParen = getPhoneCountryByDialCode(parenMatch[1]);
    if (byParen) return byParen;
  }

  const directDial = getPhoneCountryByDialCode(raw);
  if (directDial) return directDial;

  const lowered = raw.toLowerCase();
  return PHONE_COUNTRIES.find(c => c.name.toLowerCase() === lowered) || null;
}

function setupInternationalPhoneInputs(options) {
  const countryToggleButton = document.querySelector(options.countryToggleSelector);
  const countryMenu = document.querySelector(options.countryMenuSelector);
  const countryIsoInput = document.querySelector(options.countryIsoSelector);
  const phoneNumberInput = document.querySelector(options.phoneNumberSelector);
  const defaultIso = options.defaultIso || 'SG';
  const initialPhone = options.initialPhone || '';

  if (!countryToggleButton || !countryMenu || !countryIsoInput || !phoneNumberInput) {
    return null;
  }

  countryMenu.innerHTML = `
    <li class="px-2 pb-2">
      <input type="text" class="form-control form-control-sm" data-role="country-search-input" placeholder="Search country or +code" autocomplete="off">
    </li>
    <li><hr class="dropdown-divider my-1"></li>
    <li>
      <div data-role="country-options" style="max-height: 220px; overflow-y: auto;"></div>
    </li>
  `;

  const searchInput = countryMenu.querySelector('[data-role="country-search-input"]');
  const optionsContainer = countryMenu.querySelector('[data-role="country-options"]');

  const resolveCountryOrDefault = (rawValue) => {
    return resolvePhoneCountryFromSelection(rawValue)
      || getPhoneCountryByIso(countryIsoInput.value)
      || getPhoneCountryByIso(defaultIso)
      || PHONE_COUNTRIES[0];
  };

  const renderCountryOptions = (searchTerm = '') => {
    const query = String(searchTerm || '').trim().toLowerCase();
    const filtered = PHONE_COUNTRIES.filter(country => {
      if (!query) return true;
      return country.name.toLowerCase().includes(query)
        || country.iso.toLowerCase().includes(query)
        || (`+${country.dialCode}`).includes(query)
        || country.dialCode.includes(query);
    });

    optionsContainer.innerHTML = filtered.length
      ? filtered.map(country => `
          <button type="button" class="dropdown-item d-flex justify-content-between align-items-center" data-country-iso="${country.iso}">
            <span>${getCountryFlagImageHtml(country.iso, country.name)}${country.name}</span>
            <span class="text-muted">+${country.dialCode}</span>
          </button>
        `).join('')
      : '<div class="px-3 py-2 text-muted small">No countries found.</div>';
  };

  const applyCountry = (country) => {
    if (!country) return;
    countryIsoInput.value = country.iso;
    countryToggleButton.textContent = `+${country.dialCode}`;
    const lengthsText = country.validLengths.join(' or ');
    phoneNumberInput.placeholder = `Digits only (${lengthsText} digits)`;
    phoneNumberInput.title = `${country.name} numbers must be ${lengthsText} digits.`;
  };

  const extractFromStoredPhone = () => {
    const raw = String(initialPhone || '').trim();
    if (!raw.startsWith('+')) {
      return { country: resolveCountryOrDefault(countryIsoInput.value), number: normalizePhoneDigits(raw) };
    }
    const rawDigits = normalizePhoneDigits(raw);
    const sortedCodes = [...new Set(PHONE_COUNTRIES.map(c => c.dialCode))].sort((a, b) => b.length - a.length);
    for (const code of sortedCodes) {
      if (rawDigits.startsWith(code)) {
        const country = getPhoneCountryByDialCode(code) || resolveCountryOrDefault(countryIsoInput.value);
        return { country, number: rawDigits.slice(code.length) };
      }
    }
    return { country: resolveCountryOrDefault(countryIsoInput.value), number: rawDigits };
  };

  const parsed = extractFromStoredPhone();
  renderCountryOptions('');
  applyCountry(parsed.country);
  if (parsed.number) {
    phoneNumberInput.value = parsed.number;
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      renderCountryOptions(searchInput.value);
    });
  }

  optionsContainer.addEventListener('click', event => {
    const optionButton = event.target.closest('[data-country-iso]');
    if (!optionButton) {
      return;
    }
    const country = getPhoneCountryByIso(optionButton.getAttribute('data-country-iso'));
    applyCountry(country);

    if (window.bootstrap && window.bootstrap.Dropdown) {
      const dropdownInstance = window.bootstrap.Dropdown.getOrCreateInstance(countryToggleButton);
      dropdownInstance.hide();
    }
  });

  countryToggleButton.addEventListener('shown.bs.dropdown', () => {
    if (searchInput) {
      searchInput.value = '';
      renderCountryOptions('');
      setTimeout(() => searchInput.focus(), 0);
    }
  });

  phoneNumberInput.addEventListener('input', () => {
    phoneNumberInput.value = normalizePhoneDigits(phoneNumberInput.value);
  });

  return {
    getPayload() {
      const country = resolveCountryOrDefault(countryIsoInput.value);
      applyCountry(country);
      const numberDigits = normalizePhoneDigits(phoneNumberInput.value);
      return {
        phone_country: country.iso,
        phone_number: numberDigits,
        phone: numberDigits ? `+${country.dialCode} ${numberDigits}` : ''
      };
    },
    validate() {
      const country = resolveCountryOrDefault(countryIsoInput.value);
      applyCountry(country);
      const numberDigits = normalizePhoneDigits(phoneNumberInput.value);
      if (!numberDigits) {
        return { valid: true };
      }
      const isValidLength = country.validLengths.includes(numberDigits.length);
      if (!isValidLength) {
        return {
          valid: false,
          message: `${country.name} (+${country.dialCode}) requires ${country.validLengths.join(' or ')} digits.`
        };
      }

      if (Array.isArray(country.startsWith) && country.startsWith.length > 0) {
        if (!country.startsWith.includes(numberDigits.charAt(0))) {
          return {
            valid: false,
            message: `${country.name} (+${country.dialCode}) numbers must start with ${country.startsWith.join(', ')}.`
          };
        }
      }
      return { valid: true };
    }
  };
}

window.PHONE_COUNTRIES = PHONE_COUNTRIES;
window.setupInternationalPhoneInputs = setupInternationalPhoneInputs;
