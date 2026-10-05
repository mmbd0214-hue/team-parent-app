"""Opaque, database-backed sessions shared by the Web and native clients."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue_session(db, parent_id=None, password_admin=False, web=False):
    access, refresh, csrf = (secrets.token_urlsafe(48) for _ in range(3))
    now = datetime.now(timezone.utc)
    seconds = 8 * 3600 if web else 900
    with db() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO auth_sessions
            (id,parent_id,password_admin,access_hash,refresh_hash,csrf_token,access_expires_at,refresh_expires_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uuid.uuid4(), parent_id, password_admin, token_hash(access), token_hash(refresh), csrf,
             now + timedelta(seconds=seconds), now + timedelta(days=30)))
    return {"token": access, "access_token": access, "refresh_token": refresh,
            "token_type": "Bearer", "expires_in": seconds, "csrf_token": csrf}


def authenticate(db, authorization, parent_only=False, admin=False):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "尚未登入")
    token = authorization[7:]
    # Explicitly reject all historical ID/password-based credentials.
    if len(token) < 40 or ":" in token:
        raise HTTPException(401, "請重新登入")
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT s.*,p.display_name,p.line_user_id,p.is_admin,p.deleted_at
            FROM auth_sessions s LEFT JOIN parents p ON p.id=s.parent_id
            WHERE access_hash=%s AND revoked_at IS NULL AND access_expires_at>NOW()""", (token_hash(token),))
        session = cur.fetchone()
        if not session or session.get("deleted_at"):
            raise HTTPException(401, "登入已失效")
        if parent_only and session["parent_id"] is None:
            raise HTTPException(403, "請以家長帳號登入")
        if admin and not (session["password_admin"] or session.get("is_admin")):
            raise HTTPException(403, "沒有管理員權限")
        return session


def refresh_session(db, refresh_token):
    digest = token_hash(refresh_token)
    replacement_access, replacement_refresh = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
    invalid = False
    with db() as conn, conn.cursor() as cur:
        # Serialize attempts for the same refresh token, including simultaneous replays.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (digest,))
        # Keep replay revocation committed even though the request returns 401.
        cur.execute("SELECT session_id FROM used_refresh_tokens WHERE token_hash=%s", (digest,))
        used = cur.fetchone()
        if used:
            cur.execute("UPDATE auth_sessions SET revoked_at=NOW() WHERE id=%s", (used["session_id"],))
            invalid = True
        else:
            cur.execute("SELECT * FROM auth_sessions WHERE refresh_hash=%s FOR UPDATE", (digest,))
            session = cur.fetchone()
            if not session or session["revoked_at"] or session["refresh_expires_at"] <= datetime.now(timezone.utc):
                invalid = True
            else:
                cur.execute("INSERT INTO used_refresh_tokens(token_hash,session_id,expires_at) VALUES(%s,%s,%s)",
                            (digest, session["id"], session["refresh_expires_at"]))
                cur.execute("""UPDATE auth_sessions SET access_hash=%s,refresh_hash=%s,
                    access_expires_at=NOW()+INTERVAL '15 minutes' WHERE id=%s""",
                    (token_hash(replacement_access), token_hash(replacement_refresh), session["id"]))
    if invalid:
        raise HTTPException(401, "登入已失效，請重新登入")
    return {"token": replacement_access, "access_token": replacement_access,
            "refresh_token": replacement_refresh, "token_type": "Bearer", "expires_in": 900}
