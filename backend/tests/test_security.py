import jwt
import pytest

from app.core.security import create_access_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("s3cure-passphrase")
    assert verify_password("s3cure-passphrase", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_handles_malformed_hash():
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_token_roundtrip_carries_role():
    token = create_access_token("user-123", "doctor")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "doctor"


def test_expired_token_rejected():
    token = create_access_token("user-123", "doctor", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)
