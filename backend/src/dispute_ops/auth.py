from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import BaseModel


class AuthError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Session(BaseModel):
    customer_id: str
    expires_at: datetime


class SessionService:
    """Trusted test identity service: HMAC-signed tokens with a TTL.

    A document number or customer_id alone never authenticates; only a token
    issued here does.
    """

    def __init__(self, secret: bytes, ttl: timedelta, clock: Callable[[], datetime]) -> None:
        self.secret = secret
        self.ttl = ttl
        self.clock = clock

    def _sign(self, payload: bytes) -> str:
        return hmac.new(self.secret, payload, hashlib.sha256).hexdigest()

    def issue(self, customer_id: str) -> str:
        exp = self.clock() + self.ttl
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": customer_id, "exp": exp.isoformat()}).encode()
        )
        return f"{payload.decode()}.{self._sign(payload)}"

    def verify(self, token: str) -> Session:
        payload_b64, sep, sig = token.rpartition(".")
        if not sep or not hmac.compare_digest(sig, self._sign(payload_b64.encode())):
            raise AuthError("invalid")
        data = json.loads(base64.urlsafe_b64decode(payload_b64))
        session = Session(customer_id=data["sub"], expires_at=datetime.fromisoformat(data["exp"]))
        if self.clock() >= session.expires_at:
            raise AuthError("expired")
        return session
