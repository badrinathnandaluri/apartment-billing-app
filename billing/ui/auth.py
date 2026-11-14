"""Single fixed login, done properly.

Secrets (.streamlit/secrets.toml or Streamlit Cloud → Settings → Secrets):
    app_username      = "admin"
    app_password_hash = "pbkdf2_sha256$600000$..."   # python scripts/hash_password.py
The old plain `app_password` secret still works, but the app nudges you to switch.

* Constant-time comparisons, PBKDF2-SHA256 (600k iterations) hashing.
* Lockout shared by the whole server process: 5 wrong tries → 5 min, doubling after that.
  (Per-session counters can be dodged by refreshing the page.)
* Idle timeout: signed out after SESSION_IDLE_MINUTES without activity; drafts survive.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

import streamlit as st

from billing.config import BUILDING_NAME, SESSION_IDLE_MINUTES
from billing.ui import theme

MAX_TRIES = 5
BASE_LOCK_S = 300


def hash_password(password: str, iterations: int = 600_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


class _Throttle:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.failures = 0
        self.lockouts = 0
        self.locked_until = 0.0

    def remaining(self) -> int:
        return max(0, int(self.locked_until - time.time()))

    def fail(self) -> None:
        with self.lock:
            self.failures += 1
            if self.failures >= MAX_TRIES:
                self.locked_until = time.time() + BASE_LOCK_S * (2 ** self.lockouts)
                self.lockouts += 1
                self.failures = 0

    def succeed(self) -> None:
        with self.lock:
            self.failures = self.lockouts = 0
            self.locked_until = 0.0


@st.cache_resource
def _throttle() -> _Throttle:
    return _Throttle()


def _secret(name: str) -> str | None:
    try:
        v = st.secrets.get(name)
    except Exception:  # no secrets file at all
        return None
    return str(v) if v else None


def credentials_configured() -> bool:
    return bool(_secret("app_username") and (_secret("app_password_hash") or _secret("app_password")))


def check_credentials(username: str, password: str) -> bool:
    exp_user = _secret("app_username") or ""
    user_ok = hmac.compare_digest(username.strip().encode(), exp_user.encode())
    stored_hash = _secret("app_password_hash")
    if stored_hash:
        pw_ok = verify_password(password, stored_hash)
    else:
        pw_ok = hmac.compare_digest(password.encode(), (_secret("app_password") or "").encode())
    return bool(exp_user) and user_ok and pw_ok


def verify_current_password(password: str) -> bool:
    """For sensitive actions (reopening a closed month)."""
    return check_credentials(_secret("app_username") or "", password)


def using_plain_password() -> bool:
    return not _secret("app_password_hash") and bool(_secret("app_password"))


def logout() -> None:
    st.session_state.pop("auth_user", None)
    st.session_state.pop("auth_seen", None)


def require_login() -> str | None:
    """Return the signed-in username, or draw the login screen and return None."""
    now = time.time()
    user = st.session_state.get("auth_user")
    if user:
        if now - st.session_state.get("auth_seen", now) > SESSION_IDLE_MINUTES * 60:
            logout()
            st.session_state["auth_notice"] = "You were signed out after a period of inactivity. Your draft is safe."
        else:
            st.session_state["auth_seen"] = now
            return user

    _, mid, _ = st.columns([1, 1.15, 1])
    with mid:
        theme.md(
            f'<div class="login-hero"><div class="ab-logo">G</div><h2>{theme.esc(BUILDING_NAME)}</h2>'
            f'<p>Water &amp; maintenance ledger</p></div>'
        )
        if not credentials_configured():
            st.error("Login isn't configured. Add `app_username` and `app_password_hash` to the app's secrets "
                     "(see README → Secrets).")
            return None
        notice = st.session_state.pop("auth_notice", None)
        if notice:
            st.info(notice)

        throttle = _throttle()
        wait = throttle.remaining()
        with theme.card("login"):
            with st.form("login", border=False, enter_to_submit=True):
                username = st.text_input("Username", autocomplete="username")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True,
                                                  disabled=wait > 0)
            if wait > 0:
                st.warning(f"Too many wrong attempts. Try again in {wait // 60}m {wait % 60:02d}s.")
            elif submitted:
                if check_credentials(username, password):
                    throttle.succeed()
                    st.session_state["auth_user"] = username.strip()
                    st.session_state["auth_seen"] = time.time()
                    st.rerun()
                else:
                    throttle.fail()
                    time.sleep(0.6)  # slow down guessing
                    st.error("Wrong username or password.")
    return None
