import random
import smtplib
from email.mime.text import MIMEText
from flask import current_app


def generate_code():
    return str(random.randint(100000, 999999))


def send_email_code(to_email, code):
    sender_email = current_app.config["MAIL_USERNAME"]
    sender_password = current_app.config["MAIL_PASSWORD"]

    message = MIMEText(f"STOCKOLON 26 이메일 인증번호는 [{code}] 입니다.")
    message["Subject"] = "STOCKOLON 26 이메일 인증번호"
    message["From"] = sender_email
    message["To"] = to_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, sender_password)
        server.send_message(message)