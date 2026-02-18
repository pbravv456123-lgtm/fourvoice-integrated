let currentMode = null; 

document.addEventListener('DOMContentLoaded', () => {
    // Optional: Default to create
    // setMode('create');
});

function setMode(mode) {
    currentMode = mode;
    const createCard = document.getElementById('card-create');
    const joinCard = document.getElementById('card-join');
    const createForm = document.getElementById('form-create');
    const joinForm = document.getElementById('form-join');
    
    // Update hidden input for backend
    const hiddenInput = document.getElementById('selectedMode');
    if (hiddenInput) hiddenInput.value = mode;

    if (mode === 'create') {
        createCard.classList.add('selected');
        joinCard.classList.remove('selected');
        createForm.classList.remove('hidden');
        joinForm.classList.add('hidden');
    } else {
        joinCard.classList.add('selected');
        createCard.classList.remove('selected');
        joinForm.classList.remove('hidden');
        createForm.classList.add('hidden');
    }

    validateForm();
}

function validateForm() {
    const btn = document.getElementById('finishBtn');
    let isValid = false;

    if (currentMode === 'create') {
        const busType = document.getElementById('businessType').value;
        const country = document.getElementById('country').value;
        const currency = document.getElementById('currency').value;

        // Valid if all dropdowns have a value
        if (busType && country && currency) {
            isValid = true;
        }

    } else if (currentMode === 'join') {
        const code = document.getElementById('joinCode').value.trim();

        // Valid if code is not empty
        if (code.length > 0) {
            isValid = true;
        }
    }

    if (isValid) {
        btn.removeAttribute('disabled');
    } else {
        btn.setAttribute('disabled', 'true');
    }
}