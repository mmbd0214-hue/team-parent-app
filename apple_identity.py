"""Server-side Apple code exchange and encrypted credential revocation queue."""
import os
import time
import httpx
import jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException


def apple_client_secret():
    required = ['APPLE_TEAM_ID', 'APPLE_KEY_ID', 'APPLE_PRIVATE_KEY', 'APPLE_CLIENT_ID', 'IDENTITY_ENCRYPTION_KEY']
    if any(not os.getenv(key) for key in required):
        raise HTTPException(503, 'Apple 登入伺服器尚未設定完成')
    now = int(time.time())
    return jwt.encode({'iss': os.environ['APPLE_TEAM_ID'], 'iat': now, 'exp': now+300,
                       'aud': 'https://appleid.apple.com', 'sub': os.environ['APPLE_CLIENT_ID']},
                      os.environ['APPLE_PRIVATE_KEY'].replace('\\n', '\n'), algorithm='ES256',
                      headers={'kid': os.environ['APPLE_KEY_ID']})


def encrypt_identity_token(value):
    return Fernet(os.environ['IDENTITY_ENCRYPTION_KEY'].encode()).encrypt(value.encode()).decode()


def exchange_apple_code(code):
    try:
        response = httpx.post('https://appleid.apple.com/auth/token', data={
            'client_id': os.environ['APPLE_CLIENT_ID'], 'client_secret': apple_client_secret(),
            'code': code, 'grant_type': 'authorization_code'}, timeout=10)
    except httpx.HTTPError:
        raise HTTPException(503, 'Apple 暫時無法連線，請重新登入')
    if response.status_code != 200:
        raise HTTPException(401, 'Apple 登入要求已失效，請重新登入')
    value = response.json()
    if not value.get('refresh_token') or not value.get('id_token'):
        raise HTTPException(401, 'Apple 登入驗證失敗')
    return value


def drain_revocations(db):
    # A periodic worker invokes this; deletion already removed the local account.
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM provider_revocations WHERE status='pending' ORDER BY id LIMIT 20 FOR UPDATE SKIP LOCKED")
        rows = cur.fetchall()
        for row in rows:
            token = Fernet(os.environ['IDENTITY_ENCRYPTION_KEY'].encode()).decrypt(row['encrypted_token'].encode()).decode()
            try:
                response = httpx.post('https://appleid.apple.com/auth/revoke', data={
                    'client_id': os.environ['APPLE_CLIENT_ID'], 'client_secret': apple_client_secret(),
                    'token': token, 'token_type_hint': 'refresh_token'}, timeout=10)
                success = response.status_code == 200
            except httpx.HTTPError:
                success = False
            cur.execute("UPDATE provider_revocations SET status=%s,attempts=attempts+1,encrypted_token=%s WHERE id=%s",
                        ('completed' if success else 'pending', '' if success else row['encrypted_token'], row['id']))
    return len(rows)
