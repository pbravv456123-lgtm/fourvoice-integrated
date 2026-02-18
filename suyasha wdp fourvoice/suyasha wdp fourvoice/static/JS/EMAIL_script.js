document.addEventListener('DOMContentLoaded', () => {
    const codeInput = document.getElementById('verifyCode');
    const verifyBtn = document.getElementById('verifyBtn');
    const resendBtn = document.getElementById('resendBtn');
    const resendPrompt = document.getElementById('resendPrompt');
    const resendSuccess = document.getElementById('resendSuccess');
    const countdown = document.getElementById('countdown');
    const timerSpan = document.getElementById('timer');

    codeInput.addEventListener('input', () => {
        const val = codeInput.value.replace(/\D/g, '');
        codeInput.value = val;
        
        if (val.length === 6) {
            verifyBtn.classList.add('active');
            verifyBtn.disabled = false;
        } else {
            verifyBtn.classList.remove('active');
            verifyBtn.disabled = true;
        }
    });

    // LINK: Go to Setup
    verifyBtn.addEventListener('click', () => {
        if (!verifyBtn.disabled) {
            window.location.href = "/setup";
        }
    });

    if (resendBtn) {
        resendBtn.addEventListener('click', () => {
            if (resendSuccess) resendSuccess.classList.remove('hidden');
            setTimeout(() => { if (resendSuccess) resendSuccess.classList.add('hidden'); }, 5000);
            if (resendPrompt) resendPrompt.classList.add('hidden');
            if (countdown) countdown.classList.remove('hidden');

            let timeLeft = 60;
            const interval = setInterval(() => {
                timeLeft--;
                if (timerSpan) timerSpan.innerText = timeLeft;
                if (timeLeft <= 0) {
                    clearInterval(interval);
                    if (resendPrompt) resendPrompt.classList.remove('hidden');
                    if (countdown) countdown.classList.add('hidden');
                    if (timerSpan) timerSpan.innerText = "60"; 
                }
            }, 1000);
        });
    }
});