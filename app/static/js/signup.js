const sendCodeBtn = document.getElementById("send_code_btn");

sendCodeBtn.addEventListener("click", async () => {
    const emailId = document.getElementById("email_id").value;

    const email = emailId + "@goedu.kr";

    if (!emailId) {
        alert("이메일을 입력하세요.");
        return;
    }

    const response = await fetch("/auth/send-code", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ email: email })
    });

    const result = await response.json();

    if (result.success) {
        alert("인증번호가 이메일로 전송되었습니다.");
    } else {
        alert(result.message);
    }
});