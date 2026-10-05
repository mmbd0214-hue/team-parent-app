"""Native API extensions. Registered explicitly by app.py; no import-time DB writes."""
import os
import re
import secrets
import jwt
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field

from session_security import authenticate, issue_session, refresh_session, token_hash
from apple_identity import apple_client_secret, exchange_apple_code, encrypt_identity_token


def taipei_today():
    return datetime.now(timezone(timedelta(hours=8))).date()


def validate_report(method, raw_date, last5):
    if method not in {"cash", "transfer"}:
        raise HTTPException(422, "請選擇現金或轉帳")
    try:
        parsed = date.fromisoformat(raw_date)
    except (ValueError, TypeError):
        raise HTTPException(422, "請輸入有效日期")
    if method == "transfer" and not re.fullmatch(r"[0-9]{5}", last5):
        raise HTTPException(422, "帳號後五碼必須是五位數字")
    return parsed, last5 if method == "transfer" else ""


def require_linked_player(db, parent_id, player_id):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT 1 FROM parent_players pp JOIN players p ON p.id=pp.player_id
            WHERE pp.parent_id=%s AND p.id=%s AND p.active=TRUE""", (parent_id, player_id))
        if not cur.fetchone():
            raise HTTPException(403, "此球員未綁定或已停用")


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=256)


class DeletionIn(BaseModel):
    confirmation: str


class AppleIn(BaseModel):
    identity_token: str = Field(min_length=20, max_length=10000)
    challenge: str = Field(min_length=40, max_length=256)
    authorization_code: str = Field(min_length=1, max_length=10000)


apple_keys = jwt.PyJWKClient("https://appleid.apple.com/auth/keys", timeout=10)


def register_mobile_api(app, db, current_parent, fetch_matches, normalize_time):
    @app.post("/api/auth/apple/challenge")
    def apple_challenge():
        apple_client_secret()  # Fail before requesting Apple login if server credentials are incomplete.
        challenge = secrets.token_urlsafe(48)
        nonce = token_hash(secrets.token_urlsafe(48))
        with db() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO apple_challenges(challenge_hash,nonce,expires_at) VALUES(%s,%s,NOW()+INTERVAL '5 minutes')",
                        (token_hash(challenge), nonce))
        return {"challenge": challenge, "nonce": nonce}

    @app.post("/api/auth/apple")
    def apple_login(body: AppleIn):
        audience = os.getenv("APPLE_CLIENT_ID", "")
        if not audience:
            raise HTTPException(503, "Apple 登入尚未設定")
        try:
            key = apple_keys.get_signing_key_from_jwt(body.identity_token).key
            claims = jwt.decode(body.identity_token, key, algorithms=["RS256"], audience=audience,
                                issuer="https://appleid.apple.com",
                                options={"require": ["exp", "iat", "sub", "nonce"]})
        except jwt.PyJWTError:
            raise HTTPException(401, "Apple 登入驗證失敗")
        exchanged = exchange_apple_code(body.authorization_code)
        try:
            key = apple_keys.get_signing_key_from_jwt(exchanged['id_token']).key
            exchanged_claims = jwt.decode(exchanged['id_token'], key, algorithms=['RS256'], audience=audience,
                                         issuer='https://appleid.apple.com', options={'require': ['exp', 'iat', 'sub', 'nonce']})
        except jwt.PyJWTError:
            raise HTTPException(401, "Apple 登入驗證失敗")
        if exchanged_claims['sub'] != claims['sub'] or exchanged_claims['nonce'] != claims['nonce']:
            raise HTTPException(401, "Apple 帳號驗證不一致")
        with db() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE apple_challenges SET used_at=NOW() WHERE challenge_hash=%s
                AND nonce=%s AND used_at IS NULL AND expires_at>NOW() RETURNING nonce""",
                (token_hash(body.challenge), claims["nonce"]))
            if not cur.fetchone():
                raise HTTPException(401, "Apple 登入要求已失效")
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("apple:" + claims["sub"],))
            cur.execute("SELECT parent_id FROM auth_identities WHERE provider='apple' AND provider_subject=%s", (claims["sub"],))
            identity = cur.fetchone()
            if identity:
                cur.execute("SELECT * FROM parents WHERE id=%s AND deleted_at IS NULL", (identity["parent_id"],))
            else:
                cur.execute("INSERT INTO parents(line_user_id,display_name,last_login_at) VALUES(NULL,'Apple 家長',NOW()) RETURNING *")
            parent = cur.fetchone()
            if not parent:
                raise HTTPException(401, "帳號已失效")
            if not identity:
                cur.execute("INSERT INTO auth_identities(parent_id,provider,provider_subject) VALUES(%s,'apple',%s)", (parent["id"], claims["sub"]))
            cur.execute("UPDATE auth_identities SET encrypted_refresh_token=%s WHERE provider='apple' AND provider_subject=%s",
                        (encrypt_identity_token(exchanged['refresh_token']), claims['sub']))
        return {**issue_session(db, parent["id"]), "parent": parent}

    @app.post("/api/auth/refresh")
    def refresh(body: RefreshIn):
        return refresh_session(db, body.refresh_token)

    @app.post("/api/auth/logout")
    def logout(authorization: str | None = Header(default=None)):
        # Expired access tokens can still revoke their session; this is idempotent.
        if authorization and authorization.startswith("Bearer "):
            with db() as conn, conn.cursor() as cur:
                cur.execute("UPDATE auth_sessions SET revoked_at=NOW() WHERE access_hash=%s",
                            (token_hash(authorization[7:]),))
        response = JSONResponse({"ok": True})
        response.delete_cookie("team_admin", path="/")
        return response

    @app.get("/api/app-config")
    def app_config():
        return {"minimum_version": os.getenv("MINIMUM_APP_VERSION", "1.0.0"),
                "latest_version": os.getenv("LATEST_APP_VERSION", "1.0.0"),
                "maintenance": os.getenv("APP_MAINTENANCE", "0") == "1",
                "privacy_url": os.getenv("PRIVACY_URL", ""), "support_url": os.getenv("SUPPORT_URL", "")}

    @app.post("/api/auth/web-handoff")
    def handoff(authorization: str | None = Header(default=None)):
        session = authenticate(db, authorization, admin=True)
        base = os.getenv("APP_BASE_URL", "").rstrip("/")
        if urlparse(base).scheme != "https":
            raise HTTPException(503, "管理入口尚未設定 HTTPS 網址")
        code = secrets.token_urlsafe(48)
        with db() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO web_handoffs(code_hash,session_id,expires_at) VALUES(%s,%s,NOW()+INTERVAL '60 seconds')",
                        (token_hash(code), session["id"]))
        return {"url": base + "/auth/web-handoff?code=" + code, "expires_in": 60}

    @app.get("/auth/web-handoff")
    def consume_handoff(code: str):
        with db() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE web_handoffs h SET used_at=NOW() FROM auth_sessions s
                LEFT JOIN parents p ON p.id=s.parent_id WHERE h.code_hash=%s AND h.session_id=s.id
                AND h.used_at IS NULL AND h.expires_at>NOW() AND s.revoked_at IS NULL
                AND s.access_expires_at>NOW() AND (s.password_admin OR (p.is_admin AND p.deleted_at IS NULL))
                RETURNING s.parent_id,s.password_admin""", (token_hash(code),))
            row = cur.fetchone()
        if not row:
            raise HTTPException(401, "連結已失效，請重新開啟管理入口")
        session = issue_session(db, row["parent_id"], row["password_admin"], web=True)
        response = RedirectResponse("/admin", status_code=303)
        response.set_cookie("team_admin", session["access_token"], max_age=8*3600,
                            httponly=True, secure=True, samesite="strict", path="/")
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/admin/session")
    def admin_session(authorization: str | None = Header(default=None)):
        session = authenticate(db, authorization, admin=True)
        return {"ok": True, "csrf_token": session["csrf_token"]}

    @app.get("/api/events/{event_id}")
    def event_detail(event_id: int, player_id: int, authorization: str | None = Header(default=None)):
        parent = current_parent(authorization)
        with db() as conn, conn.cursor() as cur:
            cur.execute("""SELECT 1 FROM parent_players pp JOIN players p ON p.id=pp.player_id
                WHERE pp.parent_id=%s AND pp.player_id=%s AND p.active=TRUE""", (parent["id"], player_id))
            if not cur.fetchone():
                raise HTTPException(403, "無權查看此球員")
            cur.execute("SELECT * FROM events WHERE id=%s", (event_id,))
            event = cur.fetchone()
            if not event:
                raise HTTPException(404, "活動已不存在")
            cur.execute("SELECT 1 FROM event_players WHERE event_id=%s AND player_id=%s", (event_id, player_id))
            if not cur.fetchone():
                raise HTTPException(403, "此球員未受邀參加活動")
            reason = ("notice_only" if not event["survey_enabled"] else "closed" if event["status"] != "open"
                      else "deadline_passed" if event["response_deadline"] and event["response_deadline"] < taipei_today() else "")
            event["meet_time"] = normalize_time(event["meet_time"])
            matches = fetch_matches(cur, event_id)
            cur.execute("SELECT * FROM attendance WHERE event_id=%s AND player_id=%s", (event_id, player_id))
            attendance = cur.fetchone()
        return {"event": event, "matches": matches,
                "eligibility": {"player_id": player_id, "invited": True, "can_reply": not reason, "reason": reason},
                "attendance": attendance}

    @app.post("/api/me/deletion-request")
    def delete_account(body: DeletionIn, authorization: str | None = Header(default=None)):
        session = authenticate(db, authorization, parent_only=True)
        if session["created_at"] < datetime.now(timezone.utc)-timedelta(minutes=5):
            raise HTTPException(403, "請重新登入後再刪除帳號")
        if body.confirmation != "刪除帳號":
            raise HTTPException(422, "請輸入「刪除帳號」確認")
        pid = session["parent_id"]
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT line_user_id FROM parents WHERE id=%s FOR UPDATE", (pid,))
            old = cur.fetchone()
            cur.execute("DELETE FROM parent_players WHERE parent_id=%s", (pid,))
            cur.execute("""INSERT INTO provider_revocations(encrypted_token)
                SELECT encrypted_refresh_token FROM auth_identities WHERE parent_id=%s AND provider='apple'
                AND encrypted_refresh_token IS NOT NULL""", (pid,))
            cur.execute("DELETE FROM auth_identities WHERE parent_id=%s", (pid,))
            cur.execute("DELETE FROM parent_content_seen WHERE parent_id=%s", (pid,))
            cur.execute("DELETE FROM volunteer_signups WHERE parent_id=%s", (pid,))
            cur.execute("UPDATE notification_logs SET parent_id=NULL,line_user_id=NULL WHERE parent_id=%s", (pid,))
            cur.execute("UPDATE message_logs SET parent_id=NULL,line_user_id=NULL,recipient_name=NULL,message_text='[deleted]',error_message='' WHERE parent_id=%s OR line_user_id=%s", (pid, old["line_user_id"]))
            cur.execute("DELETE FROM inbound_messages WHERE parent_id=%s OR line_user_id=%s", (pid, old["line_user_id"]))
            cur.execute("UPDATE attendance SET updated_by_parent_id=NULL WHERE updated_by_parent_id=%s", (pid,))
            cur.execute("UPDATE auth_sessions SET revoked_at=NOW() WHERE parent_id=%s", (pid,))
            cur.execute("""UPDATE parents SET line_user_id=%s,display_name='已刪除帳號',picture_url='',phone='',
                is_admin=FALSE,deleted_at=NOW() WHERE id=%s""", ("deleted:"+secrets.token_hex(24), pid))
            cur.execute("INSERT INTO audit_logs(parent_id,action,resource_id) VALUES(NULL,'account_deleted',%s)", (str(pid),))
        return {"ok": True, "status": "completed"}

    @app.get("/account-deletion", response_class=HTMLResponse)
    def deletion_page():
        return """<!doctype html><html lang='zh-Hant'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
        <title>刪除球隊家長帳號</title><main><h1>刪除球隊家長帳號</h1><p>登入球隊家長 App，在「我的 → 刪除帳號」重新驗證並確認。
        亦可透過下方 Web 登入，在「我的」提出相同刪除要求。</p><p>刪除家長個資、登入、綁定及個人訊息；
        共用球員的出席與繳費紀錄不連帶刪除。</p><a href='/'>開啟 Web 家長頁面</a></main></html>"""

    @app.get("/events/{event_id}")
    def event_browser_fallback(event_id: int):
        return RedirectResponse("/?event=" + str(event_id), status_code=307)

    @app.get("/.well-known/assetlinks.json")
    def android_association():
        fingerprints = [s.strip() for s in os.getenv("ANDROID_SHA256_CERT_FINGERPRINTS", "").split(",") if s.strip()]
        if not fingerprints:
            raise HTTPException(503, "App Links 尚未設定")
        return [{"relation": ["delegate_permission/common.handle_all_urls"],
                 "target": {"namespace": "android_app", "package_name": "tw.qingshan.teamparent", "sha256_cert_fingerprints": fingerprints}}]

    @app.get("/.well-known/apple-app-site-association")
    def ios_association():
        team = os.getenv("IOS_APP_TEAM_ID", "")
        if not team:
            raise HTTPException(503, "Universal Links 尚未設定")
        return {"applinks": {"apps": [], "details": [{"appID": team + ".tw.qingshan.teamparent", "paths": ["/", "/events/*"]}]}}
