const form = document.getElementById('login_form');
AuthForm.bind(form, {
    usernum(value) {
        return /^(?:[0-9]{5}|[a-zA-Z0-9][a-zA-Z0-9_.-]{2,31})$/.test(value.trim())
            ? '' : '학번 5자리 또는 관리자 아이디를 입력해주세요.';
    },
    password: AuthForm.password
});
