"""인증 메일: 로컬 SMTP와 무료 Render용 HTTPS API. 비밀값/인증번호는 로그에 남기지 않는다."""
import secrets
import smtplib
from email.mime.text import MIMEText

import httpx
from flask import current_app


class EmailDeliveryError(Exception):
    pass


def generate_code():
    return f'{secrets.randbelow(1000000):06d}'


def send_email_code(to_email, code):
    provider = current_app.config['EMAIL_PROVIDER']
    subject = 'STOCKOLON 26 이메일 인증번호'
    text = f'STOCKOLON 26 이메일 인증번호는 [{code}]입니다. 10분 이내에 입력해주세요.'
    if provider == 'smtp':
        sender = current_app.config.get('MAIL_USERNAME')
        password = current_app.config.get('MAIL_PASSWORD')
        if not sender or not password:
            raise EmailDeliveryError('메일 발송 설정이 필요합니다.')
        message = MIMEText(text)
        message['Subject'], message['From'], message['To'] = subject, sender, to_email
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as server:
                server.login(sender, password)
                server.send_message(message)
        except (smtplib.SMTPException, OSError):
            raise EmailDeliveryError('인증 메일을 발송하지 못했습니다.') from None
        return
    sender = current_app.config.get('MAIL_FROM')
    if provider == 'brevo':
        key = current_app.config.get('BREVO_API_KEY')
        url = 'https://api.brevo.com/v3/smtp/email'
        headers = {'api-key': key or '', 'Accept': 'application/json'}
        payload = {'sender': {'name': 'STOCKOLON 26', 'email': sender},
                   'to': [{'email': to_email}], 'subject': subject, 'textContent': text}
    elif provider == 'resend':
        key = current_app.config.get('RESEND_API_KEY')
        url = 'https://api.resend.com/emails'
        headers = {'Authorization': f'Bearer {key or ""}'}
        payload = {'from': f'STOCKOLON 26 <{sender}>', 'to': [to_email], 'subject': subject, 'text': text}
    else:
        raise EmailDeliveryError('지원하지 않는 메일 발송 설정입니다.')
    if not sender or not key:
        raise EmailDeliveryError('메일 API 키와 발신 주소 설정이 필요합니다.')
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=10, follow_redirects=False)
        response.raise_for_status()
    except httpx.HTTPError:
        # 공급자 응답·요청 헤더·본문에는 인증번호와 키가 포함될 수 있으므로 출력하지 않는다.
        raise EmailDeliveryError('인증 메일을 발송하지 못했습니다. 잠시 후 다시 시도해주세요.') from None
