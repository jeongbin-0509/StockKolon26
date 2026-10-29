const resetForm = document.getElementById('reset_password_form');
let submitting = false;
resetForm.addEventListener('submit', event => {
    if (submitting) { event.preventDefault(); return; }
    submitting = true;
    const button = resetForm.querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = '변경 중…';
});
window.addEventListener('pageshow', () => {
    submitting = false;
    const button = resetForm.querySelector('button[type="submit"]');
    button.disabled = false;
    button.textContent = '비밀번호 변경';
});
