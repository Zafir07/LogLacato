"""Dependências comuns das rotas: sessão do banco, usuário logado, perfil mínimo, auditoria."""
from collections.abc import Callable, Iterator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import ROLE_RANK, decode_token
from app.database.session import SessionLocal
from app.models import AuditLog, User

bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def user_from_token(db: Session, token: str | None) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido ou expirado",
                            headers={"WWW-Authenticate": "Bearer"}) from None
    user = db.get(User, int(claims["sub"]))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "usuário inativo ou inexistente")
    return user


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    return user_from_token(db, creds.credentials if creds else None)


def require(min_role: str) -> Callable[..., User]:
    """Exige pelo menos o perfil indicado (leitura < coletor < gestor < admin)."""

    def dep(user: User = Depends(current_user)) -> User:
        if ROLE_RANK[user.role] < ROLE_RANK[min_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requer perfil {min_role} ou superior")
        return user

    return dep


def audit(db: Session, request: Request | None, user: User | None, action: str, entity: str,
          entity_id: object = None, details: dict | None = None) -> None:
    db.add(AuditLog(
        user_id=user.id if user else None, action=action, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None, details=details,
        ip=request.client.host if request and request.client else None,
    ))


def paginate(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    return (page - 1) * page_size, page_size
