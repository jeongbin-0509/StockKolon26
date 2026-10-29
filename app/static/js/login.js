const form = document.getElementById('login_form');
AuthForm.bind(form, {
    usernum(value) {
        return /^(?:[0-9]{5}|[a-zA-Z0-9][a-zA-Z0-9_.-]{2,31})$/.test(value.trim())
            ? '' : '아이디 또는 학번을 확인해주세요.';
    },
    password: AuthForm.password
});
