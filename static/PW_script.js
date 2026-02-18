document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('resetForm');
    const resetBtn = document.getElementById('resetBtn');
    
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const confirmInput = document.getElementById('confirmPassword');
    const inputs = [emailInput, passwordInput, confirmInput];

    // --- REAL-TIME VALIDATION (Makes button dark) ---
    function checkFormValidity() {
        const email = emailInput.value.trim();
        const pass = passwordInput.value;
        const confirm = confirmInput.value;

        // 1. Check Email exists and has @gmail.com (basic check)
        const isEmailValid = email.includes('@gmail.com');
        
        // 2. Check Password Strength
        let isPassStrong = false;
        if (pass.length >= 8 && 
            /[a-z]/.test(pass) && 
            /[A-Z]/.test(pass) && 
            /[0-9]/.test(pass)) {
            isPassStrong = true;
        }

        // 3. Check Passwords Match
        const isMatch = (pass === confirm) && (pass !== "");

        // IF ALL GOOD -> Make button dark
        if (isEmailValid && isPassStrong && isMatch) {
            resetBtn.classList.add('active');
            resetBtn.disabled = false;
        } else {
            resetBtn.classList.remove('active');
            resetBtn.disabled = true;
        }
    }

    // Run the check every time user types
    inputs.forEach(input => {
        input.addEventListener('input', () => {
            // Also clear error text while typing
            const errorMsg = input.parentElement.querySelector('.error-msg') || input.parentElement.parentElement.querySelector('.error-msg');
            clearError(input, errorMsg);
            input.setCustomValidity("");
            
            // Run the validation logic
            checkFormValidity();
        });
    });

    // --- FINAL SUBMISSION LOGIC ---
    form.addEventListener('submit', (e) => {
        e.preventDefault(); 
        
        // One final check just to be safe
        let isValid = !resetBtn.disabled; 

        // If the button was enabled, we assume visual validation passed.
        // We can do a quick re-verify of specific error messages if needed:
        if (passwordInput.value !== confirmInput.value) {
            document.getElementById('confirmError').style.display = 'block';
            isValid = false;
        }

        if (isValid) {
            console.log("Reset Valid. Submitting to Python...");
            // Submits form -> App.py -> Redirects to Email Page
            form.submit(); 
        }
    });
});

function showError(input, msgElement) {
    input.classList.add('error');
    if (msgElement) {
        msgElement.style.display = 'block';
    }
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