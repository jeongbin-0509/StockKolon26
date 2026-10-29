// 오류는 제출 또는 해당 필드를 편집한 뒤에만 표시한다.
window.AuthForm = {
    bind(form, validators) {
        form.noValidate = true;
        function validate(input) {
            const message = validators[input.id]?.(input.value) || '';
            const error = document.getElementById(`${input.id}_errormsg`);
            input.setAttribute('aria-invalid', message ? 'true' : 'false');
            if (error) { if (message) error.textContent = message; error.hidden = !message; }
            return !message;
        }
        for (const id of Object.keys(validators)) {
            const input = document.getElementById(id);
            input.addEventListener('blur', () => validate(input));
            input.addEventListener('input', () => { if (input.getAttribute('aria-invalid') === 'true') validate(input); });
            input.addEventListener('change', () => { if (input.getAttribute('aria-invalid') === 'true') validate(input); });
        }
        form.addEventListener('submit', event => {
            const invalid = Object.keys(validators).map(id => document.getElementById(id)).filter(input => !validate(input));
            if (invalid.length) { event.preventDefault(); invalid[0].focus(); return; }
            const button = form.querySelector('button[type="submit"]');
            button.disabled = true;
            button.textContent = form.id === 'login_form' ? '로그인 중…' : '가입 처리 중…';
        });
        window.addEventListener('pageshow', () => {
            const button = form.querySelector('button[type="submit"]');
            button.disabled = false;
            button.textContent = form.id === 'login_form' ? '로그인' : '회원가입';
        });
        return validate;
    },
    usernum(value) { return /^[0-9]{5}$/.test(value) ? '' : '학번 5자리를 숫자로 입력해주세요.'; },
    password(value) { return value.length >= 6 ? '' : '비밀번호를 6자 이상 입력해주세요.'; },
    email(value) { return /^[a-zA-Z0-9._%+\-]+$/.test(value) ? '' : '학교 이메일의 @ 앞부분만 입력해주세요.'; }
};
