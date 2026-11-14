"""Prints an app_password_hash line for your secrets.

    python scripts/hash_password.py
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64  # noqa: E402
import hashlib  # noqa: E402
import secrets  # noqa: E402


def hash_password(password: str, iterations: int = 600_000) -> str:
    # Same format as billing.ui.auth.hash_password (kept dependency-free: no Streamlit needed).
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


if __name__ == "__main__":
    pw = getpass.getpass("New password: ")
    if len(pw) < 8:
        sys.exit("Use at least 8 characters.")
    if pw != getpass.getpass("Repeat: "):
        sys.exit("Passwords don't match.")
    print(f'\napp_password_hash = "{hash_password(pw)}"')
