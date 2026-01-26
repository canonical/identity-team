import pyotp


def generate_totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()
