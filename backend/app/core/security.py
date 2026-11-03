"""Senhas (Argon2) e tokens de acesso (JWT HS256) — o papel do Cognito no relatório."""
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_hasher = PasswordHasher()

ROLE_RANK = {"leitura": 0, "coletor": 1, "gestor": 2, "admin": 3}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _secret() -> str:
    secret = get_settings().jwt_secret
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET precisa ter pelo menos 32 caracteres (defina no .env)")
    return secret


def create_token(user_id: int, role: str) -> tuple[str, datetime]:
    exp = datetime.now(UTC) + timedelta(minutes=get_settings().jwt_expire_minutes)
    token = jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, _secret(), algorithm="HS256")
    return token, exp


def decode_token(token: str) -> dict:
    """Levanta jwt.PyJWTError se o token for inválido ou expirado."""
    return jwt.decode(token, _secret(), algorithms=["HS256"], options={"require": ["exp", "sub"]})
