"""POST /sessions, JWT issue/verify, organisation binding, rate limiting."""
from __future__ import annotations

import hmac
import threading
import time
from dataclasses import dataclass

import jwt
from fastapi import APIRouter, Depends, Request, Response

from .config import Settings
from .errors import DidomiError
from .models import Session, SessionInput

TOKEN_TTL_S = 3600
router = APIRouter()


@dataclass(frozen=True)
class Principal:
    organization_id: str
    key: str


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/sessions", response_model=Session, tags=["sessions"], summary="Create a new session")
def create_session(payload: SessionInput, settings: Settings = Depends(settings_of)) -> Session:
    if payload.type != "api-key":
        raise DidomiError(400, "Invalid authentication information")
    match = next((k for k in settings.keys if hmac.compare_digest(k.key, payload.key)
                  and hmac.compare_digest(k.secret, payload.secret)), None)
    if match is None:
        raise DidomiError(400, "Invalid authentication information")
    now = int(time.time())
    token = jwt.encode({"sub": match.key, "organization_id": match.organization_id, "type": "api-key",
                        "iat": now, "exp": now + TOKEN_TTL_S, "iss": "didomi-sim"},
                       settings.jwt_secret, algorithm="HS256")
    return Session(type="api-key", key=match.key, access_token=token)


def principal(request: Request, settings: Settings = Depends(settings_of)) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise DidomiError(401, "No auth token")
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.ExpiredSignatureError:
        raise DidomiError(401, "jwt expired")
    except jwt.InvalidTokenError:
        raise DidomiError(401, "invalid token")
    return Principal(organization_id=claims["organization_id"], key=claims["sub"])


def check_org(who: Principal, organization_id: str) -> None:
    if organization_id != who.organization_id:
        raise DidomiError(403, f"You are not allowed to access the organization {organization_id}")


class RateLimiter:
    """Fixed 15-second window per organisation, IETF RateLimit draft-7 headers."""

    def __init__(self, limit: int, window_s: int):
        self.limit, self.window = limit, window_s
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def hit(self, org: str, response: Response) -> None:
        now = time.monotonic()
        with self._lock:
            start, count = self._windows.get(org, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            count += 1
            self._windows[org] = (start, count)
        reset = max(1, int(round(self.window - (now - start))))
        headers = {"RateLimit": f"limit={self.limit}, remaining={max(0, self.limit - count)}, reset={reset}",
                   "RateLimit-Policy": f"{self.limit};w={self.window}"}
        if count > self.limit:
            raise DidomiError(429, "Too many requests", headers={**headers, "Retry-After": str(reset)})
        response.headers.update(headers)


def rate_limited(request: Request, response: Response, who: Principal = Depends(principal)) -> Principal:
    request.app.state.rate_limiter.hit(who.organization_id, response)
    return who
