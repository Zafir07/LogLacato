"""Registra cada requisição com um identificador, o status e o tempo de resposta.

O identificador volta no cabeçalho X-Request-ID, para cruzar o log com o erro
que o usuário viu na tela.
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger("app.requests")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("%s %s falhou [req=%s]", request.method, request.url.path, request_id)
            raise
        elapsed = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        log.info(
            "%s %s -> %s em %.1f ms [req=%s]",
            request.method, request.url.path, response.status_code, elapsed, request_id,
        )
        return response
