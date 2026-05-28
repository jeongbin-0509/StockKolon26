/* /login을 처리하는 js 파일 */

// form 가져오기
const form = document.getElementById("login_form");

// submit 이벤트 감지
form.addEventListener("submit", (event) => {

    // input 값 가져오기
    const usernum = document.getElementById("usernum").value;
    const password = document.getElementById("password").value;

    // 아이디 길이 검사
    if (usernum.length != 5) {
        console.log("submit 실행");
        // form 제출 막기
        event.preventDefault();

        // 학번은 5글자 이상이어야 합니다.

        return;
    }

    // 비밀번호 길이 검사
    if (password.length < 6) {

        event.preventDefault();

        alert("비밀번호는 6글자 이상이어야 합니다.");

        return;
    }

});

const signup_btn = document.getElementById("moveto_signup_btn");

signup_btn.addEventListener("click", event => {
    location.href = "/auth/signup"
});