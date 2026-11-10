"""Send approved products to Etsy as DRAFT listings (never auto-activated).

Flow: OAuth 2.0 with PKCE (scopes listings_w listings_r shops_r) -> createDraftListing ->
upload listing images (mockups) -> upload digital files -> set type=download.
The listing stays a draft in Shop Manager until YOU review and publish it there.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import secrets
import urllib.parse
from pathlib import Path

from ..config import settings
from ..db import get_setting, set_setting
from ..services import Budget, ExternalServiceError, http_request

AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
API = "https://api.etsy.com/v3/application"
SCOPES = "listings_w listings_r shops_r"


class EtsyAuthRequired(RuntimeError):
    pass


def oauth_start() -> str:
    if not settings.etsy_api_key:
        raise EtsyAuthRequired("Set ETSY_API_KEY first (see Settings > Credentials).")
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    set_setting("etsy_oauth_pending", {"verifier": verifier, "state": state})
    q = {"response_type": "code", "redirect_uri": settings.etsy_redirect_uri, "scope": SCOPES,
         "client_id": settings.etsy_api_key, "state": state, "code_challenge": challenge,
         "code_challenge_method": "S256"}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def oauth_callback(code: str, state: str) -> dict:
    pending = get_setting("etsy_oauth_pending") or {}
    if not pending or pending.get("state") != state:
        raise EtsyAuthRequired("OAuth state mismatch - please start the connection again.")
    resp = http_request("POST", TOKEN_URL, data={"grant_type": "authorization_code", "client_id": settings.etsy_api_key,
                                                 "redirect_uri": settings.etsy_redirect_uri, "code": code,
                                                 "code_verifier": pending["verifier"]})
    if resp.status_code >= 400:
        raise ExternalServiceError(f"Etsy token exchange failed: {resp.text[:300]}")
    tok = resp.json()
    _store(tok)
    set_setting("etsy_oauth_pending", {})
    me = _api("GET", "/users/me")
    shop_id = me.get("shop_id")
    set_setting("etsy_account", {"user_id": me.get("user_id"), "shop_id": shop_id})
    return {"connected": True, "shop_id": shop_id}


def _store(tok: dict) -> None:
    exp = (dt.datetime.utcnow() + dt.timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)).isoformat()
    # Stored locally in the app database on your computer (never sent anywhere except Etsy).
    set_setting("etsy_tokens", {"access_token": tok["access_token"], "refresh_token": tok["refresh_token"],
                                "expires_at": exp})


def _token() -> str:
    t = get_setting("etsy_tokens") or {}
    if not t.get("access_token"):
        raise EtsyAuthRequired("Connect your Etsy shop first (Settings > Connect Etsy).")
    if dt.datetime.fromisoformat(t["expires_at"]) < dt.datetime.utcnow():
        resp = http_request("POST", TOKEN_URL, data={"grant_type": "refresh_token", "client_id": settings.etsy_api_key,
                                                     "refresh_token": t["refresh_token"]})
        if resp.status_code >= 400:
            raise EtsyAuthRequired("Etsy session expired - reconnect your shop.")
        _store(resp.json())
        t = get_setting("etsy_tokens")
    return t["access_token"]


def _api(method: str, path: str, **kw) -> dict:
    key = settings.etsy_api_key + (f":{settings.etsy_shared_secret}" if settings.etsy_shared_secret else "")
    headers = {"x-api-key": key, "Authorization": f"Bearer {_token()}"}
    resp = http_request(method, API + path, headers=headers, timeout=120, **kw)
    Budget.record("etsy", "api_call", 0.0, units=1, note=path)
    if resp.status_code >= 400:
        raise ExternalServiceError(f"Etsy {method} {path} failed ({resp.status_code}): {resp.text[:400]}")
    return resp.json() if resp.content else {}


def is_connected() -> bool:
    return bool((get_setting("etsy_tokens") or {}).get("access_token"))


def send_draft(listing: dict, data_dir: Path, taxonomy_id: int | None = None) -> dict:
    acct = get_setting("etsy_account") or {}
    shop_id = acct.get("shop_id")
    if not shop_id:
        raise EtsyAuthRequired("Connect your Etsy shop first.")
    if not taxonomy_id:
        raise ValueError("Choose an Etsy category (taxonomy id) in Listing Studio before sending.")
    body = {"quantity": 999, "title": listing["title"], "description": listing["description"],
            "price": listing["price"], "who_made": "i_did", "when_made": "made_to_order", "taxonomy_id": taxonomy_id,
            "type": "download", "tags": ",".join(listing["tags"]), "is_supply": "false"}
    created = _api("POST", f"/shops/{shop_id}/listings", data=body)
    lid = created["listing_id"]
    for rank, m in enumerate(listing.get("mockups", [])[:10], start=1):
        with open(data_dir / m["path"], "rb") as fh:
            _api("POST", f"/shops/{shop_id}/listings/{lid}/images", files={"image": fh}, data={"rank": rank})
    for rank, d in enumerate(listing.get("deliverables", [])[:5], start=1):
        with open(data_dir / d["path"], "rb") as fh:
            _api("POST", f"/shops/{shop_id}/listings/{lid}/files", files={"file": fh},
                 data={"name": d["name"], "rank": rank})
    return {"listing_id": lid, "state": "draft",
            "message": "Draft created on Etsy. Review and publish it in Shop Manager > Listings > Drafts."}
