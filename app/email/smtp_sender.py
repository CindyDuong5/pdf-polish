# app/email/smtp_sender.py
from __future__ import annotations

import os
import re
import ssl
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterable, Optional, Sequence, Tuple


@dataclass
class EmailAttachment:
    filename: str
    content_type: str  # e.g. "application/pdf"
    data: bytes


def _parse_email_from(value: str) -> Tuple[str, str]:
    """
    Accepts either:
      - 'Mainline Fire Protection <support@mainlinefire.com>'
      - 'support@mainlinefire.com'
    Returns (display_name, email_address)

    This function is tolerant of a missing trailing '>' in env values.
    """
    v = (value or "").strip().strip('"')

    # Normal case: has <...>
    m = re.match(r"^(.*)<([^>]+)>$", v)
    if m:
        name = (m.group(1) or "").strip().strip('"')
        email = (m.group(2) or "").strip()
        return (name or "Mainline Fire Protection", email)

    # Tolerate missing closing ">"
    m2 = re.match(r"^(.*)<([^>]+)$", v)
    if m2:
        name = (m2.group(1) or "").strip().strip('"')
        email = (m2.group(2) or "").strip().rstrip(">")
        return (name or "Mainline Fire Protection", email)

    # Just an email (or invalid string)
    return ("Mainline Fire Protection", v)


def send_email_brevo_smtp(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    cc_emails: Optional[Iterable[str]] = None,
    attachments: Sequence[EmailAttachment] = (),
) -> None:
    """
    Sends an email via Brevo SMTP.

    Required env:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM
    Optional env:
      EMAIL_REPLY_TO
    """
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]

    # EMAIL_FROM can be:
    #   Mainline Fire Protection <support@mainlinefire.com>
    #   support@mainlinefire.com
    from_name, from_email = _parse_email_from(os.environ["EMAIL_FROM"])

    # Reply-To should be a real mailbox (no trailing dot)
    reply_to = os.getenv("EMAIL_REPLY_TO", from_email).strip().rstrip(".")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to

    # CC list (also used for SMTP envelope recipients)
    cc_list = [e.strip() for e in (cc_emails or []) if e and e.strip()]
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    # Plain + HTML parts
    msg.set_content(text_body or "")
    msg.add_alternative(html_body or "", subtype="html")

    # Attachments
    for att in attachments:
        if not att.content_type or "/" not in att.content_type:
            maintype, subtype = "application", "octet-stream"
        else:
            maintype, subtype = att.content_type.split("/", 1)

        msg.add_attachment(
            att.data,
            maintype=maintype,
            subtype=subtype,
            filename=att.filename,
        )

    # Send
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(user, password)

        # IMPORTANT: Brevo requires SMTP envelope-from to be a valid email address.
        to_addrs = [to_email] + cc_list
        server.send_message(msg, from_addr=from_email, to_addrs=to_addrs)