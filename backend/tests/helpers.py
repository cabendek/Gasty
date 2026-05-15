import email as _email_module
from email.header import decode_header, make_header
from pathlib import Path


def load_eml(path: str | Path) -> dict:
    """Parse a .eml file and return an email_data dict for parsers."""
    with open(path, "rb") as f:
        raw = f.read()

    msg = _email_module.message_from_bytes(raw)

    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    from_addr = msg.get("From", "")
    date_str = msg.get("Date", "")
    message_id = msg.get("Message-ID", "unknown").strip("<>")

    body_plain = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                body_plain = payload.decode(charset, errors="replace")
                break

    return {
        "message_id": message_id,
        "subject": subject,
        "from": from_addr,
        "date": date_str,
        "body_plain": body_plain,
    }
