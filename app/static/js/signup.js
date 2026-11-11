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
const codeInput = document.getElementById('email_code');
const verifyCodeBtn = document.getElementById('verify_code_btn');
const verificationStatus = document.getElementById('verification_status');
const status = document.getElementById('email_status');
let countdown;
let sentEmail = '';
let verifiedEmail = '';
let verifiedCode = '';
function showStatus(message, state) {
    status.textContent = message;
    status.dataset.state = state;
    status.hidden = false;
}
function showVerificationStatus(message, state) {
    verificationStatus.textContent = message;
    verificationStatus.dataset.state = state;
    verificationStatus.hidden = false;
}
function resetVerification(message = '') {
    verifiedEmail = '';
    verifiedCode = '';
    verifyCodeBtn.dataset.verified = 'false';
    verifyCodeBtn.textContent = '인증번호 확인';
    verifyCodeBtn.disabled = !/^[0-9]{6}$/.test(codeInput.value);
    if (message) showVerificationStatus(message, 'pending');
    else verificationStatus.hidden = true;
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
        sentEmail = emailId;
        showStatus('인증번호를 보냈습니다. 학교 메일함을 확인해주세요.', 'success');
        resetVerification();
        codeInput.focus();
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
    resetVerification(sentEmail ? '이메일이 변경되었습니다. 새 주소로 인증번호를 받아주세요.' : '');
    if (countdown) {
        clearInterval(countdown); countdown = null;
        sendCodeBtn.disabled = false; sendCodeBtn.textContent = '인증번호 받기';
        showStatus('변경한 이메일로 인증번호를 다시 받아주세요.', 'pending');
    }
});
codeInput.addEventListener('input', () => {
    codeInput.value = codeInput.value.replace(/\D/g, '').slice(0, 6);
    if (codeInput.value !== verifiedCode || emailInput.value !== verifiedEmail) resetVerification();
});
verifyCodeBtn.addEventListener('click', async () => {
    if (!validate(emailInput)) { emailInput.focus(); return; }
    if (!validate(codeInput)) { codeInput.focus(); return; }
    verifyCodeBtn.disabled = true;
    verifyCodeBtn.textContent = '확인 중…';
    showVerificationStatus('인증번호를 확인하고 있습니다.', 'pending');
    try {
        const emailId = emailInput.value;
        const code = codeInput.value;
        const response = await fetch('/auth/verify-code', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email: `${emailId}@goedu.kr`, code}), signal: AbortSignal.timeout(15000)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) throw new Error(data.message || '인증번호를 확인하지 못했습니다.');
        if (emailId !== emailInput.value || code !== codeInput.value) throw new Error('입력 내용이 변경되었습니다. 다시 확인해주세요.');
        verifiedEmail = emailId;
        verifiedCode = code;
        verifyCodeBtn.dataset.verified = 'true';
        verifyCodeBtn.textContent = '인증 완료';
        showVerificationStatus(data.message, 'success');
    } catch (error) {
        resetVerification();
        showVerificationStatus(error.name === 'TimeoutError' ? '응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.' : error.message, 'error');
    }
});
signupForm.addEventListener('submit', event => {
    if (verifiedEmail !== emailInput.value || verifiedCode !== codeInput.value) {
        event.preventDefault();
        showVerificationStatus('회원가입 전에 인증번호 확인 버튼을 눌러주세요.', 'error');
        codeInput.focus();
    }
});
