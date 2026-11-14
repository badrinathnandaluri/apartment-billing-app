import sys
from pathlib import Path

from billing.ui.auth import _Throttle, hash_password, verify_password

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_hash_round_trip_and_rejects_wrong_password():
    h = hash_password("correct horse", iterations=1000)
    assert h.startswith("pbkdf2_sha256$1000$")
    assert verify_password("correct horse", h)
    assert not verify_password("Correct horse", h)
    assert not verify_password("correct horse", "not-a-hash")
    assert hash_password("correct horse", iterations=1000) != h      # fresh salt every time


def test_script_hash_is_accepted_by_the_app():
    from hash_password import hash_password as script_hash
    assert verify_password("demo-pass-123", script_hash("demo-pass-123", iterations=1000))


def test_lockout_after_five_failures_and_reset_on_success():
    t = _Throttle()
    for _ in range(4):
        t.fail()
    assert t.remaining() == 0
    t.fail()
    assert 290 <= t.remaining() <= 300
    t.succeed()
    assert t.remaining() == 0
