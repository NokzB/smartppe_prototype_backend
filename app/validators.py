from app.config import BLOCKED_EMAIL_DOMAINS


def is_blocked_email_domain(email: str) -> bool:
    domain = email.split("@")[-1].lower()
    return domain in BLOCKED_EMAIL_DOMAINS