document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('confirmText');
    const deleteBtn = document.getElementById('deleteBtn');

    input.addEventListener('input', () => {
        // Only enable button if text matches exactly
        if (input.value === 'DELETE') {
            deleteBtn.disabled = false;
        } else {
            deleteBtn.disabled = true;
        }
    });
});