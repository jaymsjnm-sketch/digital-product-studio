"""Optional Canva Connect integration: import a product PDF into your Canva account as an
editable design (Design Import API, scope design:content:write). Canva does not accept SVG imports.

After import, open the design in Canva and use Share > Template link yourself; only then is it
honest to advertise the listing as a "Canva template". Until that link exists, listings never
mention Canva (enforced by the listing checks).
Requires CANVA_CLIENT_ID / CANVA_CLIENT_SECRET from https://www.canva.com/developers/ .
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from pathlib import Path

from ..config import settings
from ..db import get_setting, set_setting
from ..services import ExternalServiceError, http_request

AUTH = "https://www.canva.com/api/oauth/authorize"
TOKEN = "https://api.canva.com/rest/v1/oauth/token"
API = "https://api.canva.com/rest/v1"
REDIRECT = "http://127.0.0.1:8000/api/canva/oauth/callback"


def configured() -> bool:
    return bool(settings.canva_client_id and settings.canva_client_secret)


def oauth_start() -> str:
    if not configured():
        raise RuntimeError("Canva is not configured (CANVA_CLIENT_ID / CANVA_CLIENT_SECRET).")
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    set_setting("canva_pending", {"verifier": verifier, "state": state})
    return AUTH + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": settings.canva_client_id, "redirect_uri": REDIRECT,
        "scope": "design:content:write design:meta:read asset:write", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})


def oauth_callback(code: str, state: str) -> dict:
    pend = get_setting("canva_pending") or {}
    if pend.get("state") != state:
        raise RuntimeError("Canva OAuth state mismatch")
    basic = base64.b64encode(f"{settings.canva_client_id}:{settings.canva_client_secret}".encode()).decode()
    r = http_request("POST", TOKEN, headers={"Authorization": f"Basic {basic}"},
                     data={"grant_type": "authorization_code", "code": code, "code_verifier": pend["verifier"],
                           "redirect_uri": REDIRECT})
    if r.status_code >= 400:
        raise ExternalServiceError(f"Canva token exchange failed: {r.text[:300]}")
    set_setting("canva_tokens", r.json())
    return {"connected": True}


def import_pdf(pdf: Path, title: str) -> dict:
    tok = (get_setting("canva_tokens") or {}).get("access_token")
    if not tok:
        raise RuntimeError("Connect Canva first.")
    meta = base64.b64encode(json.dumps({"title_base64": base64.b64encode(title[:50].encode()).decode()}).encode()).decode()
    r = http_request("POST", f"{API}/imports", data=Path(pdf).read_bytes(),
                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/octet-stream",
                              "Import-Metadata": json.dumps({"title_base64": base64.b64encode(title[:50].encode()).decode(),
                                                             "mime_type": "application/pdf"})})
    if r.status_code >= 400:
        raise ExternalServiceError(f"Canva import failed: {r.text[:300]}")
    job = r.json()["job"]
    for _ in range(30):
        if job.get("status") in ("success", "failed"):
            break
        time.sleep(2)
        job = http_request("GET", f"{API}/imports/{job['id']}", headers={"Authorization": f"Bearer {tok}"}).json()["job"]
    if job.get("status") != "success":
        raise ExternalServiceError(f"Canva import did not finish: {job}")
    d = job["result"]["designs"][0]
    _ = meta
    return {"design_id": d["id"], "edit_url": d["urls"]["edit_url"],
            "next_step": "Open the design in Canva, check it, then Share > Template link. Paste that link into the listing."}
