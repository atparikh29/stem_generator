"""Username/password auth: hashing, register, login, password reset."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes import (
    ForgotBody, LoginBody, RegisterBody, ResetBody,
    forgot_password, login, register, reset_password,
)
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


def test_forgot_then_reset_changes_password_and_signs_in():
    with _mem() as db:
        register(RegisterBody(username="erin", password="old"), db)
        issued = forgot_password(ForgotBody(username="erin"), db)
        token = issued["reset_token"]
        assert token and issued["expires_in_minutes"] == 30

        out = reset_password(ResetBody(username="erin", token=token, new_password="fresh"), db)
        assert "session_id" in out and "password_hash" not in out       # signed in, hash hidden

        assert login(LoginBody(username="erin", password="fresh"), db)["id"] == out["id"]
        with pytest.raises(HTTPException):                              # old password no longer works
            login(LoginBody(username="erin", password="old"), db)


def test_forgot_unknown_user_is_generic_no_token():
    with _mem() as db:
        res = forgot_password(ForgotBody(username="nobody"), db)
        assert res["ok"] is True and "reset_token" not in res           # no user enumeration


def test_reset_rejects_wrong_token_and_reused_token():
    with _mem() as db:
        register(RegisterBody(username="frank", password="pw"), db)
        token = forgot_password(ForgotBody(username="frank"), db)["reset_token"]
        with pytest.raises(HTTPException) as bad:
            reset_password(ResetBody(username="frank", token="not-it", new_password="x"), db)
        assert bad.value.status_code == 400
        # A good token works once, then is cleared (can't be replayed).
        reset_password(ResetBody(username="frank", token=token, new_password="x"), db)
        with pytest.raises(HTTPException) as reused:
            reset_password(ResetBody(username="frank", token=token, new_password="y"), db)
        assert reused.value.status_code == 400


def test_reset_rejects_expired_token():
    with _mem() as db:
        student = register(RegisterBody(username="gina", password="pw"), db)
        token = forgot_password(ForgotBody(username="gina"), db)["reset_token"]
        # Force the token to have already expired.
        from app.models import Student
        row = db.get(Student, student["id"])
        row.reset_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.add(row); db.commit()
        with pytest.raises(HTTPException) as exp:
            reset_password(ResetBody(username="gina", token=token, new_password="x"), db)
        assert exp.value.status_code == 400
