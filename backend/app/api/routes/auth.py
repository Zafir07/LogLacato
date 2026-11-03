"""Login e usuários (perfis: admin, gestor, coletor, leitura)."""
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import audit, current_user, get_db, paginate, require
from app.core.security import create_token, hash_password, verify_password
from app.models import User
from app.schemas.api import LoginIn, Page, TokenOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/v1", tags=["Autenticação e usuários"])

# Hash fixo para gastar o mesmo tempo quando o e-mail não existe (não revela quais e-mails existem).
_DUMMY = hash_password("senha-que-nao-existe-1234")
_FAILS: dict[str, list[float]] = {}
MAX_FAILS, WINDOW_S = 5, 300


def _too_many(key: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _FAILS.get(key, []) if now - t < WINDOW_S]
    _FAILS[key] = recent
    return len(recent) >= MAX_FAILS


@router.post("/auth/login", response_model=TokenOut, summary="Entrar e receber o token de acesso")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = f"{body.email}|{request.client.host if request.client else '-'}"
    if _too_many(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "muitas tentativas; aguarde 5 minutos")
    user = db.scalar(select(User).where(User.email == body.email))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY)
    if not user or not ok or not user.active:
        _FAILS.setdefault(key, []).append(time.monotonic())
        audit(db, request, None, "login_falhou", "user", None, {"email": body.email})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "e-mail ou senha incorretos")
    _FAILS.pop(key, None)
    token, exp = create_token(user.id, user.role)
    audit(db, request, user, "login", "user", user.id)
    db.commit()
    return TokenOut(access_token=token, expires_at=exp, user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut, summary="Usuário logado")
def me(user: User = Depends(current_user)):
    return user


@router.get("/users", response_model=Page[UserOut], summary="Listar usuários")
def list_users(page: int = 1, page_size: int = 50, q: str | None = Query(None, max_length=80),
               db: Session = Depends(get_db), _: User = Depends(require("admin"))):
    stmt = select(User)
    if q:
        stmt = stmt.where(User.name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, size = paginate(page, page_size)
    items = db.scalars(stmt.order_by(User.name).offset(off).limit(size)).all()
    return Page(items=items, total=total, page=page, page_size=size)


@router.post("/users", response_model=UserOut, status_code=201, summary="Criar usuário")
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require("admin"))):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "já existe um usuário com esse e-mail")
    user = User(name=body.name, email=body.email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    audit(db, request, admin, "criar", "user", user.id, {"email": user.email, "role": user.role})
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut, summary="Alterar usuário")
def update_user(user_id: int, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require("admin"))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "usuário não encontrado")
    if user.id == admin.id and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(400, "você não pode desativar nem rebaixar a si mesmo")
    changes = body.model_dump(exclude_none=True)
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
        changes["password"] = "alterada"
    for k, v in changes.items():
        if k != "password":
            setattr(user, k, v)
    audit(db, request, admin, "alterar", "user", user.id, changes)
    db.commit()
    return user
