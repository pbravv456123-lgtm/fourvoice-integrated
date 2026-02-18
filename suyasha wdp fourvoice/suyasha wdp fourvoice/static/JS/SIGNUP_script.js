document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('signupForm');
    const inputs = form.querySelectorAll('input[type="text"], input[type="email"], input[type="password"]');

    form.addEventListener('submit', (e) => {
        // 1. Stop default submission
        e.preventDefault(); 
        
        let isValid = true;

        // --- 1. General Check for Empty Fields ---
        inputs.forEach(input => {
            const errorMsg = input.parentElement.querySelector('.error-msg') || input.parentElement.parentElement.querySelector('.error-msg');
            
            // Clear old custom validity
            input.setCustomValidity("");

            // Basic empty check
            if (input.value.trim() === '') {
                showError(input, errorMsg);
                // If it's the password field, reset text to "required" if it's empty
                if (input.id === 'password') errorMsg.textContent = "Password is required";
                isValid = false;
            } else {
                clearError(input, errorMsg);
            }
        });

        // --- 2. Email Validation (@gmail.com popup) ---
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

        // --- 3. Password Strength Validation ---
        const passwordInput = document.getElementById('password');
        const passwordErrorMsg = document.getElementById('passwordError');
        const passVal = passwordInput.value;

        // Only validate strength if password is not empty
        if (passVal !== '') {
            let passError = "";

            // Condition 2: Length < 8
            if (passVal.length < 8) {
                passError = "Password length is less than 8 characters";
            } 
            // Condition 3a: No lowercase
            else if (!/[a-z]/.test(passVal)) { 
                passError = "Password does not contain lowercase alphabets";
            } 
            // Condition 3b: No uppercase
            else if (!/[A-Z]/.test(passVal)) { 
                passError = "Password does not contain uppercase alphabets";
            } 
            // Condition 4: No numbers
            else if (!/[0-9]/.test(passVal)) { 
                passError = "Password does not contain numbers";
            }

            if (passError) {
                passwordInput.classList.add('error');
                passwordErrorMsg.textContent = passError;
                passwordErrorMsg.style.display = 'block';
                isValid = false;
            }
        }

        // --- 4. Confirm Password Match ---
        const confirmPassword = document.getElementById('confirmPassword');
        const confirmErrorMsg = document.getElementById('confirmError');

        // Only check match if both fields have values
        if (passwordInput.value && confirmPassword.value) {
            // Condition 1: Mismatch
            if (passwordInput.value !== confirmPassword.value) {
                confirmPassword.classList.add('error');
                confirmErrorMsg.textContent = "Passwords do not match";
                confirmErrorMsg.style.display = 'block';
                isValid = false;
            }
        }

        // --- 5. CHECKBOX VALIDATION (NEW) ---
        const termsCheckbox = document.getElementById('terms');
        const termsErrorMsg = document.getElementById('termsError');

        if (!termsCheckbox.checked) {
            // Show the error message we added in HTML
            if (termsErrorMsg) termsErrorMsg.style.display = 'block';
            isValid = false;
        } else {
            if (termsErrorMsg) termsErrorMsg.style.display = 'none';
        }

        // --- 6. FINAL SUBMISSION ---
        if (isValid) {
            console.log("Form is valid. Submitting to server...");
            form.submit(); 
        }
    });

    // Clear errors when user types
    inputs.forEach(input => {
        input.addEventListener('input', () => {
            const errorMsg = input.parentElement.querySelector('.error-msg') || input.parentElement.parentElement.querySelector('.error-msg');
            clearError(input, errorMsg);
            input.setCustomValidity("");
        });
    });

    // --- NEW: Clear Checkbox Error on Click ---
    const termsCheckbox = document.getElementById('terms');
    const termsErrorMsg = document.getElementById('termsError');
    if (termsCheckbox) {
        termsCheckbox.addEventListener('change', () => {
            if (termsCheckbox.checked) {
                if (termsErrorMsg) termsErrorMsg.style.display = 'none';
            }
        });
    }
});

function showError(input, msgElement) {
    input.classList.add('error');
    if (msgElement) {
        if (input.id === 'confirmPassword' && input.value === '') {
            msgElement.textContent = "Please confirm your password";
        }
        msgElement.style.display = 'block';
    }
}

function clearError(input, msgElement) {
    input.classList.remove('error');
    if (msgElement) {
        msgElement.style.display = 'none';
    }
}

function togglePassword(inputId, toggleIcon) {
    const input = document.getElementById(inputId);
    const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
    input.setAttribute('type', type);
}