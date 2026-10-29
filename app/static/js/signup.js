const signupForm = document.getElementById('signup_form');
const passwordInput = document.getElementById('password');
const validate = AuthForm.bind(signupForm, {
    name: value => value.trim() ? '' : '이름을 입력해주세요.',
    usernum: AuthForm.usernum,
    email_id: AuthForm.email,
    email_code: value => /^[0-9]{6}$/.test(value) ? '' : '인증번호 6자리를 숫자로 입력해주세요.',
    password: AuthForm.password,
    password_check: value => value && value === passwordInput.value ? '' : '입력한 비밀번호와 일치하지 않습니다.',
    club_id: value => value ? '' : '소속 동아리 또는 미선택을 선택해주세요.'
});
passwordInput.addEventListener('input', () => {
    const confirmation = document.getElementById('password_check');
    if (confirmation.value) validate(confirmation);
});
const sendCodeBtn = document.getElementById('send_code_btn');
const emailInput = document.getElementById('email_id');
const status = document.getElementById('email_status');
let countdown;
function showStatus(message, state) {
    status.textContent = message;
    status.dataset.state = state;
    status.hidden = false;
}
sendCodeBtn.addEventListener('click', async () => {
    if (!validate(emailInput)) { emailInput.focus(); return; }
    const emailId = emailInput.value;
    sendCodeBtn.disabled = true;
    sendCodeBtn.textContent = '발송 중…';
    showStatus('인증번호를 보내고 있습니다.', 'pending');
    try {
        const response = await fetch('/auth/send-code', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email: `${emailId}@goedu.kr`}), signal: AbortSignal.timeout(15000)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) throw new Error(data.message || '인증 메일을 보내지 못했습니다. 잠시 후 다시 시도해주세요.');
        if (emailId !== emailInput.value) throw new Error('이메일이 변경되었습니다. 새 주소로 다시 인증번호를 받아주세요.');
        showStatus('인증번호를 보냈습니다. 학교 메일함을 확인해주세요.', 'success');
        document.getElementById('email_code').focus();
        let seconds = 60;
        sendCodeBtn.textContent = `${seconds}초 후 재발송`;
        countdown = setInterval(() => {
            seconds -= 1;
            if (seconds <= 0) { clearInterval(countdown); sendCodeBtn.disabled = false; sendCodeBtn.textContent = '인증번호 재발송'; }
            else sendCodeBtn.textContent = `${seconds}초 후 재발송`;
        }, 1000);
    } catch (error) {
        showStatus(error.name === 'TimeoutError' ? '응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.' : error.message, 'error');
        sendCodeBtn.disabled = false;
        sendCodeBtn.textContent = '인증번호 받기';
    }
});
emailInput.addEventListener('input', () => {
    if (countdown) {
        clearInterval(countdown); countdown = null;
        sendCodeBtn.disabled = false; sendCodeBtn.textContent = '인증번호 받기';
        showStatus('변경한 이메일로 인증번호를 다시 받아주세요.', 'pending');
    }
});
