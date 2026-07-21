"""Username/password auth: hashing, register, login."""
import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes import LoginBody, RegisterBody, login, register
from app.auth import hash_password, verify_password


def _mem() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng, expire_on_commit=False)


def test_hash_roundtrip_and_wrong_password():
    h = hash_password("hunter2")
    assert h.startswith("pbkdf2_sha256$")
    assert "hunter2" not in h                 # never stores plaintext
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)
    assert not verify_password("hunter2", "garbage")


def test_hash_is_salted():
    assert hash_password("same") != hash_password("same")


def test_register_then_login_resumes_session():
    with _mem() as db:
        # register/login return a dict: the public user fields + a fresh session_id
        user = register(RegisterBody(username="bob", password="pw", skill="kinematics", difficulty=1), db)
        assert user["username"] == "bob"
        assert user["onboarded"] and user["current_skill"] == "kinematics"
        assert "session_id" in user and "password_hash" not in user
        again = login(LoginBody(username="bob", password="pw"), db)
        assert again["id"] == user["id"]           # same user/account row
        assert again["session_id"] != user["session_id"]  # but a new login session


def test_duplicate_username_rejected():
    with _mem() as db:
        register(RegisterBody(username="carol", password="pw"), db)
        with pytest.raises(HTTPException) as exc:
            register(RegisterBody(username="carol", password="other"), db)
        assert exc.value.status_code == 409


def test_wrong_password_and_unknown_user_rejected():
    with _mem() as db:
        register(RegisterBody(username="dave", password="right"), db)
        with pytest.raises(HTTPException) as e1:
            login(LoginBody(username="dave", password="WRONG"), db)
        assert e1.value.status_code == 401
        with pytest.raises(HTTPException) as e2:
            login(LoginBody(username="ghost", password="x"), db)
        assert e2.value.status_code == 401
