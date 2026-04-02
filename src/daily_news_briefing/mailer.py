from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


@dataclass(slots=True)
class GenericSMTPMailer:
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool = True

    def send(
        self,
        *,
        mail_from: str,
        mail_to: list[str],
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        message = MIMEMultipart("alternative")
        message["From"] = mail_from
        message["To"] = ", ".join(mail_to)
        message["Subject"] = subject
        message.attach(MIMEText(text_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

        if self.use_ssl:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as server:
                server.login(self.username, self.password)
                server.sendmail(mail_from, mail_to, message.as_string())
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(mail_from, mail_to, message.as_string())


class QQSMTPMailer(GenericSMTPMailer):
    def __init__(self, username: str, password: str, host: str = "smtp.qq.com", port: int = 465) -> None:
        super().__init__(host=host, port=port, username=username, password=password, use_ssl=True)

