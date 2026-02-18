document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('signinForm');
    const inputs = form.querySelectorAll('input[type="email"], input[type="password"]');

    form.addEventListener('submit', (e) => {
        e.preventDefault(); 
        let isValid = true;

        // 1. Check Empty Fields
        inputs.forEach(input => {
            const errorMsg = input.parentElement.querySelector('.error-msg') || input.parentElement.parentElement.querySelector('.error-msg');
            input.setCustomValidity("");

            if (input.value.trim() === '') {
                showError(input, errorMsg);
                isValid = false;
            } else {
                clearError(input, errorMsg);
            }
        });

        // 2. Check Gmail
        const emailInput = document.getElementById('email');
        if (emailInput.value.trim() !== '') {
            if (!emailInput.value.includes('@gmail.com')) {
                emailInput.classList.add('error');
                emailInput.setCustomValidity("Please include '@gmail.com' in the email address.");
                emailInput.reportValidity();
                isValid = false;
            } else {
                emailInput.setCustomValidity("");
            }
        }

        if (isValid) {
            console.log("Sign In Valid. Submitting...");
            form.submit(); // Sends data to app.py
        }
    });

    inputs.forEach(input => {
        input.addEventListener('input', () => {
            const errorMsg = input.parentElement.querySelector('.error-msg') || input.parentElement.parentElement.querySelector('.error-msg');
            clearError(input, errorMsg);
            input.setCustomValidity("");
        });
    });
});

function showError(input, msgElement) {
    input.classList.add('error');
    if (msgElement) msgElement.style.display = 'block';
}

function clearError(input, msgElement) {
    input.classList.remove('error');
    if (msgElement) msgElement.style.display = 'none';
}

function togglePassword(inputId, toggleIcon) {
    const input = document.getElementById(inputId);
    const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
    input.setAttribute('type', type);
}