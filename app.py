
import os
import secrets
import base64
import hashlib
import hmac
import json
from datetime import date

import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MOCK_LOGIN = os.getenv("MOCK_LOGIN", "0") == "1"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-now")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "").strip()
LINE_LIFF_ID = os.getenv("LINE_LIFF_ID", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
VOLUNTEER_WEBAPP_URL = os.getenv("VOLUNTEER_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbwRsh7TUzKrHldH5-YJV_wH6JvtNOEu78mx0z0a7wKlMi8-6hwrthgR5DcJLe_A5lQxyw/exec").strip()

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 尚未設定")

app = FastAPI(title="球隊家長 App")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def new_bind_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def init_db():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS parents (
                id BIGSERIAL PRIMARY KEY,
                line_user_id TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                picture_url TEXT
            );

            CREATE TABLE IF NOT EXISTS players (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                team TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS parent_players (
                parent_id BIGINT NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
                player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                PRIMARY KEY(parent_id, player_id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                event_date DATE NOT NULL,
                location TEXT NOT NULL,
                meal_price INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id BIGSERIAL PRIMARY KEY,
                event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                attendance_status TEXT NOT NULL,
                leave_reason TEXT DEFAULT '',
                player_meals INTEGER NOT NULL DEFAULT 0,
                parent_meals INTEGER NOT NULL DEFAULT 0,
                UNIQUE(event_id, player_id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id BIGSERIAL PRIMARY KEY,
                player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                amount INTEGER NOT NULL,
                due_date DATE,
                status TEXT NOT NULL DEFAULT 'unpaid',
                note TEXT DEFAULT ''
            );
            """)

            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE")
            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT ''")
            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT TRUE")
            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")

            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS number TEXT DEFAULT ''")
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE")
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS bind_code TEXT")
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS max_parents INTEGER NOT NULL DEFAULT 2")

            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'practice'")
            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS response_deadline DATE")
            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS meal_enabled BOOLEAN NOT NULL DEFAULT TRUE")

            cur.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS practice_duration TEXT DEFAULT 'full'")
            cur.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS attendance_note TEXT DEFAULT ''")

            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS meet_time TIME")
            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS meet_time_tbd BOOLEAN NOT NULL DEFAULT FALSE")

            cur.execute("""
            CREATE TABLE IF NOT EXISTS event_matches (
                id BIGSERIAL PRIMARY KEY,
                event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                match_order INTEGER NOT NULL DEFAULT 1,
                game_time TIME,
                game_time_tbd BOOLEAN NOT NULL DEFAULT FALSE,
                opponent TEXT NOT NULL DEFAULT ''
            )
            """)

            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_players_bind_code
            ON players(bind_code)
            WHERE bind_code IS NOT NULL
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS event_players (
                event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                PRIMARY KEY(event_id, player_id)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS notification_logs (
                id BIGSERIAL PRIMARY KEY,
                event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                parent_id BIGINT REFERENCES parents(id) ON DELETE SET NULL,
                player_id BIGINT REFERENCES players(id) ON DELETE SET NULL,
                notification_type TEXT NOT NULL,
                line_user_id TEXT,
                status TEXT NOT NULL,
                error_message TEXT DEFAULT '',
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS volunteer_slots (
                id BIGSERIAL PRIMARY KEY,
                volunteer_date DATE NOT NULL,
                group_name TEXT NOT NULL,
                capacity INTEGER NOT NULL DEFAULT 1,
                note TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                UNIQUE(volunteer_date, group_name)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS volunteer_signups (
                id BIGSERIAL PRIMARY KEY,
                slot_id BIGINT NOT NULL REFERENCES volunteer_slots(id) ON DELETE CASCADE,
                parent_id BIGINT NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
                player_id BIGINT REFERENCES players(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(slot_id, parent_id)
            )
            """)


            cur.execute("""
            CREATE TABLE IF NOT EXISTS message_logs (
                id BIGSERIAL PRIMARY KEY,
                parent_id BIGINT REFERENCES parents(id) ON DELETE SET NULL,
                line_user_id TEXT,
                recipient_name TEXT,
                target_type TEXT NOT NULL,
                target_label TEXT DEFAULT '',
                message_text TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT DEFAULT '',
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id BIGSERIAL PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                message_text TEXT NOT NULL,
                target_type TEXT NOT NULL DEFAULT 'all',
                target_values JSONB NOT NULL DEFAULT '[]'::jsonb,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """)

            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_announcements_created_at
            ON announcements(created_at DESC)
            """)


            cur.execute("ALTER TABLE announcements ADD COLUMN IF NOT EXISTS source_key TEXT")
            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_announcements_source_key
            ON announcements(source_key)
            WHERE source_key IS NOT NULL
            """)


            cur.execute("ALTER TABLE message_logs ADD COLUMN IF NOT EXISTS batch_id TEXT")


            cur.execute("""
            CREATE TABLE IF NOT EXISTS inbound_messages (
                id BIGSERIAL PRIMARY KEY,
                parent_id BIGINT REFERENCES parents(id) ON DELETE SET NULL,
                line_user_id TEXT NOT NULL,
                message_type TEXT NOT NULL DEFAULT 'text',
                message_text TEXT DEFAULT '',
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """)

            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_inbound_messages_parent
            ON inbound_messages(parent_id, received_at DESC)
            """)




            # historical LINE messages -> App announcements
            # 同一次群發只匯入一則公告；後台直接回覆單一家長的對話不匯入。
            cur.execute("""
                WITH grouped AS (
                    SELECT
                        CASE
                            WHEN batch_id IS NOT NULL AND BTRIM(batch_id) <> ''
                                THEN 'batch:' || batch_id
                            ELSE
                                'legacy:' ||
                                TO_CHAR(sent_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD') ||
                                ':' || COALESCE(target_type,'') ||
                                ':' || COALESCE(target_label,'') ||
                                ':' || MD5(COALESCE(message_text,''))
                        END AS source_key,
                        MIN(sent_at) AS created_at,
                        MAX(target_type) AS target_type,
                        MAX(target_label) AS target_label,
                        MAX(message_text) AS message_text,
                        ARRAY_REMOVE(ARRAY_AGG(DISTINCT parent_id), NULL) AS parent_ids
                    FROM message_logs
                    WHERE NOT (
                        target_type='parent'
                        AND target_label='單一家長'
                    )
                    GROUP BY
                        CASE
                            WHEN batch_id IS NOT NULL AND BTRIM(batch_id) <> ''
                                THEN 'batch:' || batch_id
                            ELSE
                                'legacy:' ||
                                TO_CHAR(sent_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD') ||
                                ':' || COALESCE(target_type,'') ||
                                ':' || COALESCE(target_label,'') ||
                                ':' || MD5(COALESCE(message_text,''))
                        END
                )
                SELECT source_key,created_at,target_type,target_label,message_text,parent_ids
                FROM grouped
                ORDER BY created_at
            """)
            old_message_groups = cur.fetchall()

            allowed_teams = {"U10", "U12", "U13", "U15"}

            for old in old_message_groups:
                # 如果新版功能已經曾同步過同一則公告，就不要再建立重複資料。
                cur.execute("""
                    SELECT 1
                    FROM announcements
                    WHERE message_text=%s
                      AND target_type=%s
                      AND ABS(EXTRACT(EPOCH FROM (created_at - %s))) < 300
                    LIMIT 1
                """, (
                    old["message_text"],
                    old["target_type"],
                    old["created_at"],
                ))
                if cur.fetchone():
                    continue

                target_values = []

                if old["target_type"] == "team":
                    label = old["target_label"] or ""
                    normalized = (
                        label.replace(",", "、")
                             .replace("，", "、")
                             .replace(" ", "、")
                    )
                    target_values = [
                        x for x in normalized.split("、")
                        if x in allowed_teams
                    ]

                elif old["target_type"] == "parent":
                    target_values = [
                        str(pid) for pid in (old["parent_ids"] or [])
                    ]

                cur.execute("""
                    INSERT INTO announcements(
                        title,message_text,target_type,target_values,
                        active,created_at,source_key
                    )
                    VALUES('',%s,%s,%s::jsonb,TRUE,%s,%s)
                    ON CONFLICT DO NOTHING
                """, (
                    old["message_text"],
                    old["target_type"],
                    json.dumps(target_values, ensure_ascii=False),
                    old["created_at"],
                    old["source_key"],
                ))

            # legacy events without event_players -> assign all active players once
            cur.execute("""
                INSERT INTO event_players(event_id, player_id)
                SELECT e.id, p.id
                FROM events e
                CROSS JOIN players p
                WHERE p.active=TRUE
                  AND NOT EXISTS (
                    SELECT 1 FROM event_players ep WHERE ep.event_id=e.id
                  )
                ON CONFLICT DO NOTHING
            """)

            # assign bind codes to old players
            cur.execute("SELECT id FROM players WHERE bind_code IS NULL")
            ids = [r["id"] for r in cur.fetchall()]
            for pid in ids:
                for _ in range(20):
                    code = new_bind_code()
                    try:
                        cur.execute("UPDATE players SET bind_code=%s WHERE id=%s", (code, pid))
                        break
                    except psycopg.errors.UniqueViolation:
                        conn.rollback()
                        continue
        conn.commit()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def home():
    return FileResponse(os.path.join(BASE, "static", "index.html"))


@app.get("/admin")
def admin_page():
    return FileResponse(os.path.join(BASE, "static", "admin.html"))



@app.get("/manifest.webmanifest")
def manifest_file():
    return FileResponse(
        os.path.join(BASE, "static", "manifest.webmanifest"),
        media_type="application/manifest+json"
    )


@app.get("/service-worker.js")
def service_worker_file():
    return FileResponse(
        os.path.join(BASE, "static", "service-worker.js"),
        media_type="application/javascript"
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {"liff_id": LINE_LIFF_ID, "mock_login": MOCK_LOGIN, "volunteer_url": VOLUNTEER_WEBAPP_URL}


# ---------------- Parent LINE / LIFF auth ----------------

class LineAuth(BaseModel):
    access_token: str | None = None


@app.post("/api/auth/line")
async def auth_line(payload: LineAuth):
    if MOCK_LOGIN and (not payload.access_token or payload.access_token == "mock"):
        profile = {"userId": "mock-parent-001", "displayName": "測試家長", "pictureUrl": ""}
    else:
        if not payload.access_token:
            raise HTTPException(401, "缺少 LINE access token")

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.line.me/v2/profile",
                headers={"Authorization": f"Bearer {payload.access_token}"}
            )

        if r.status_code != 200:
            raise HTTPException(401, "LINE 登入驗證失敗")

        profile = r.json()

    line_user_id = profile.get("userId")
    if not line_user_id:
        raise HTTPException(401, "無法取得 LINE User ID")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM parents WHERE line_user_id=%s", (line_user_id,))
            row = cur.fetchone()

            if not row:
                cur.execute("""
                    INSERT INTO parents(line_user_id,display_name,picture_url,last_login_at)
                    VALUES(%s,%s,%s,NOW())
                    RETURNING *
                """, (
                    line_user_id,
                    profile.get("displayName", "LINE 家長"),
                    profile.get("pictureUrl", "")
                ))
                row = cur.fetchone()
            else:
                cur.execute("""
                    UPDATE parents
                    SET display_name=%s,picture_url=%s,last_login_at=NOW()
                    WHERE id=%s
                    RETURNING *
                """, (
                    profile.get("displayName", row["display_name"]),
                    profile.get("pictureUrl", ""),
                    row["id"]
                ))
                row = cur.fetchone()

        conn.commit()

    return {"token": f"parent:{row['id']}", "parent": row}


def current_parent(authorization):
    if not authorization or not authorization.startswith("Bearer parent:"):
        raise HTTPException(401, "尚未登入")
    try:
        pid = int(authorization.split(":")[-1])
    except Exception:
        raise HTTPException(401, "登入資訊錯誤")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM parents WHERE id=%s", (pid,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(401, "家長不存在")

    return row



@app.get("/api/announcements")
def parent_announcements(
    authorization: str | None = Header(default=None)
):
    parent = current_parent(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            # 目前家長所綁定球員的組別
            cur.execute("""
                SELECT DISTINCT p.team
                FROM parent_players pp
                JOIN players p ON p.id=pp.player_id
                WHERE pp.parent_id=%s
                  AND p.active=TRUE
            """, (parent["id"],))
            teams = {r["team"] for r in cur.fetchall()}

            result = []
            seen = set()

            # -------------------------------------------------
            # A. 正式 announcements
            # -------------------------------------------------
            cur.execute("""
                SELECT
                    a.id,
                    a.title,
                    a.message_text,
                    a.target_type,
                    a.target_values,
                    a.created_at
                FROM announcements a
                WHERE a.active=TRUE
                ORDER BY a.created_at DESC,a.id DESC
                LIMIT 300
            """)
            rows = cur.fetchall()

            for row in rows:
                target_type = row["target_type"]
                target_values = row["target_values"] or []

                visible = False

                if target_type == "all":
                    visible = True

                elif target_type == "team":
                    visible = any(team in teams for team in target_values)

                elif target_type == "parent":
                    visible = str(parent["id"]) in [str(x) for x in target_values]

                if not visible:
                    continue

                key = (
                    row["message_text"],
                    target_type,
                    row["created_at"].date() if row["created_at"] else None,
                )

                seen.add(key)
                result.append({
                    "id": f"a-{row['id']}",
                    "title": row["title"],
                    "message_text": row["message_text"],
                    "target_type": target_type,
                    "target_values": target_values,
                    "created_at": row["created_at"],
                    "source": "announcement",
                })

            # -------------------------------------------------
            # B. 歷史 message_logs
            # 直接即時合併，不再依賴 startup backfill。
            # -------------------------------------------------

            # B1. 全部 / 組別群發
            cur.execute("""
                WITH grouped AS (
                    SELECT
                        CASE
                            WHEN batch_id IS NOT NULL AND BTRIM(batch_id) <> ''
                                THEN 'batch:' || batch_id
                            ELSE
                                'legacy:' ||
                                TO_CHAR(sent_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD') ||
                                ':' || COALESCE(target_type,'') ||
                                ':' || COALESCE(target_label,'') ||
                                ':' || MD5(COALESCE(message_text,''))
                        END AS group_id,
                        MIN(sent_at) AS sent_at,
                        MAX(target_type) AS target_type,
                        MAX(target_label) AS target_label,
                        MAX(message_text) AS message_text
                    FROM message_logs
                    WHERE target_type IN ('all','team')
                    GROUP BY
                        CASE
                            WHEN batch_id IS NOT NULL AND BTRIM(batch_id) <> ''
                                THEN 'batch:' || batch_id
                            ELSE
                                'legacy:' ||
                                TO_CHAR(sent_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD') ||
                                ':' || COALESCE(target_type,'') ||
                                ':' || COALESCE(target_label,'') ||
                                ':' || MD5(COALESCE(message_text,''))
                        END
                )
                SELECT *
                FROM grouped
                ORDER BY sent_at DESC
                LIMIT 300
            """)
            logs = cur.fetchall()

            allowed_teams = {"U10", "U12", "U13", "U15"}

            for row in logs:
                target_type = row["target_type"]
                target_values = []

                if target_type == "all":
                    visible = True

                else:
                    label = row["target_label"] or ""
                    normalized = (
                        label.replace(",", "、")
                             .replace("，", "、")
                             .replace("/", "、")
                             .replace(" ", "、")
                    )
                    target_values = [
                        x for x in normalized.split("、")
                        if x in allowed_teams
                    ]

                    # 某些舊紀錄 target_label 可能格式不固定，
                    # 再直接從字串搜尋 U10/U12/U13/U15。
                    if not target_values:
                        target_values = [
                            t for t in allowed_teams
                            if t in label
                        ]

                    visible = any(team in teams for team in target_values)

                if not visible:
                    continue

                key = (
                    row["message_text"],
                    target_type,
                    row["sent_at"].date() if row["sent_at"] else None,
                )

                if key in seen:
                    continue

                seen.add(key)
                result.append({
                    "id": row["group_id"],
                    "title": "",
                    "message_text": row["message_text"],
                    "target_type": target_type,
                    "target_values": target_values,
                    "created_at": row["sent_at"],
                    "source": "message_log",
                })

            # B2. 指定家長歷史訊息
            # 只撈這個 parent_id 曾實際收到的群發。
            cur.execute("""
                WITH grouped AS (
                    SELECT
                        CASE
                            WHEN batch_id IS NOT NULL AND BTRIM(batch_id) <> ''
                                THEN 'batch:' || batch_id
                            ELSE
                                'legacy-parent:' ||
                                TO_CHAR(sent_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD') ||
                                ':' || MD5(COALESCE(message_text,''))
                        END AS group_id,
                        MIN(sent_at) AS sent_at,
                        MAX(message_text) AS message_text
                    FROM message_logs
                    WHERE parent_id=%s
                      AND target_type='parent'
                      AND COALESCE(target_label,'') <> '單一家長'
                    GROUP BY
                        CASE
                            WHEN batch_id IS NOT NULL AND BTRIM(batch_id) <> ''
                                THEN 'batch:' || batch_id
                            ELSE
                                'legacy-parent:' ||
                                TO_CHAR(sent_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD') ||
                                ':' || MD5(COALESCE(message_text,''))
                        END
                )
                SELECT *
                FROM grouped
                ORDER BY sent_at DESC
                LIMIT 200
            """, (parent["id"],))
            parent_logs = cur.fetchall()

            for row in parent_logs:
                key = (
                    row["message_text"],
                    "parent",
                    row["sent_at"].date() if row["sent_at"] else None,
                )

                if key in seen:
                    continue

                seen.add(key)
                result.append({
                    "id": row["group_id"],
                    "title": "",
                    "message_text": row["message_text"],
                    "target_type": "parent",
                    "target_values": [str(parent["id"])],
                    "created_at": row["sent_at"],
                    "source": "message_log",
                })

            result.sort(
                key=lambda x: x["created_at"],
                reverse=True
            )

            return result[:300]


# ---------------- Parent self binding ----------------

class BindCodeIn(BaseModel):
    code: str


@app.post("/api/bind/preview")
def bind_preview(body: BindCodeIn, authorization: str | None = Header(default=None)):
    parent = current_parent(authorization)
    code = body.code.strip().upper()

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,name,team,number,active,bind_code,max_parents
                FROM players
                WHERE bind_code=%s
            """, (code,))
            player = cur.fetchone()

            if not player or not player["active"]:
                raise HTTPException(404, "找不到此綁定碼")

            cur.execute("SELECT COUNT(*) n FROM parent_players WHERE player_id=%s", (player["id"],))
            linked = cur.fetchone()["n"]

            cur.execute("""
                SELECT 1 FROM parent_players
                WHERE parent_id=%s AND player_id=%s
            """, (parent["id"], player["id"]))
            already = bool(cur.fetchone())

    return {
        "player": {
            "id": player["id"],
            "name": player["name"],
            "team": player["team"],
            "number": player["number"],
        },
        "linked_parents": linked,
        "max_parents": player["max_parents"],
        "already_bound": already,
        "can_bind": already or linked < player["max_parents"],
    }


@app.post("/api/bind/confirm")
def bind_confirm(body: BindCodeIn, authorization: str | None = Header(default=None)):
    parent = current_parent(authorization)
    code = body.code.strip().upper()

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,name,team,number,active,max_parents
                FROM players
                WHERE bind_code=%s
                FOR UPDATE
            """, (code,))
            player = cur.fetchone()

            if not player or not player["active"]:
                raise HTTPException(404, "找不到此綁定碼")

            cur.execute("""
                SELECT 1 FROM parent_players
                WHERE parent_id=%s AND player_id=%s
            """, (parent["id"], player["id"]))

            if cur.fetchone():
                return {"ok": True, "already_bound": True, "player": player}

            cur.execute("SELECT COUNT(*) n FROM parent_players WHERE player_id=%s", (player["id"],))
            linked = cur.fetchone()["n"]

            if linked >= player["max_parents"]:
                raise HTTPException(409, "此球員已達家長綁定數量上限")

            cur.execute("""
                INSERT INTO parent_players(parent_id,player_id)
                VALUES(%s,%s)
            """, (parent["id"], player["id"]))

        conn.commit()

    return {"ok": True, "already_bound": False, "player": player}


# ---------------- Parent APIs ----------------

@app.get("/api/me")
def me(authorization: str | None = Header(default=None)):
    p = current_parent(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pl.*
                FROM players pl
                JOIN parent_players pp ON pp.player_id=pl.id
                WHERE pp.parent_id=%s AND pl.active=TRUE
                ORDER BY pl.team,pl.name
            """, (p["id"],))
            players = cur.fetchall()

    return {
        "parent": p,
        "players": players,
        "needs_binding": len(players) == 0
    }



@app.get("/api/me/admin-session")
def parent_admin_session(
    authorization: str | None = Header(default=None)
):
    parent = current_parent(authorization)

    if not parent.get("is_admin", False):
        raise HTTPException(403, "此 LINE 帳號沒有管理員權限")

    return {
        "ok": True,
        "token": f"parent-admin:{parent['id']}",
        "parent_id": parent["id"],
        "display_name": parent["display_name"],
    }


@app.get("/api/events")
def parent_events(authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.id,e.title,e.event_date,e.location,e.meal_price,
                       e.status,e.event_type,e.response_deadline,e.meet_time,e.meet_time_tbd
                FROM events e
                WHERE e.id IN (
                    SELECT ep.event_id
                    FROM event_players ep
                    JOIN parent_players pp ON pp.player_id=ep.player_id
                    WHERE pp.parent_id=%s
                )
                  AND e.event_date >= %s
                ORDER BY e.event_date,e.id
            """, (p["id"], date.today()))
            rows = cur.fetchall()
            result=[]
            for row in rows:
                result.append({
                    **row,
                    "event_date": row["event_date"].isoformat() if row["event_date"] else None,
                    "response_deadline": row["response_deadline"].isoformat() if row["response_deadline"] else None,
                    "meet_time": normalize_time_value(row.get("meet_time")),
                    "matches": fetch_event_matches(cur,row["id"]),
                })
            return result


@app.get("/api/players/{player_id}/attendance")
def player_attendance(player_id: int, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM parent_players
                WHERE parent_id=%s AND player_id=%s
            """, (p["id"], player_id))

            if not cur.fetchone():
                raise HTTPException(403, "無權查看此球員")

            cur.execute("SELECT * FROM attendance WHERE player_id=%s", (player_id,))
            return cur.fetchall()


class AttendanceIn(BaseModel):
    player_id: int
    attendance_status: str
    leave_reason: str = ""
    practice_duration: str = "full"
    attendance_note: str = ""
    player_meals: int = 0
    parent_meals: int = 0


@app.put("/api/events/{event_id}/attendance")
def save_attendance(event_id: int, body: AttendanceIn, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)

    if body.attendance_status not in ("attend", "leave", "maybe"):
        raise HTTPException(400, "attendance_status 錯誤")

    if body.player_meals < 0 or body.parent_meals < 0:
        raise HTTPException(400, "餐點數量不可為負數")

    if body.practice_duration not in ("full", "morning_leave", "afternoon_leave", "half"):
        # "half" is kept only for compatibility with existing records.
        raise HTTPException(400, "practice_duration 錯誤")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM parent_players
                WHERE parent_id=%s AND player_id=%s
            """, (p["id"], body.player_id))

            if not cur.fetchone():
                raise HTTPException(403, "無權修改此球員")

            cur.execute("""
                SELECT 1 FROM event_players
                WHERE event_id=%s AND player_id=%s
            """, (event_id, body.player_id))

            if not cur.fetchone():
                raise HTTPException(403, "此球員不在本活動名單")

            cur.execute("""
                SELECT meal_enabled
                FROM events
                WHERE id=%s AND status='open'
                  AND (response_deadline IS NULL OR response_deadline >= %s)
            """, (event_id, date.today()))

            event_row = cur.fetchone()
            if not event_row:
                raise HTTPException(403, "活動已截止")

            player_meals = body.player_meals if event_row["meal_enabled"] else 0
            parent_meals = body.parent_meals if event_row["meal_enabled"] else 0

            cur.execute("""
                INSERT INTO attendance(
                    event_id,player_id,attendance_status,
                    leave_reason,practice_duration,attendance_note,
                    player_meals,parent_meals
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(event_id,player_id) DO UPDATE SET
                    attendance_status=EXCLUDED.attendance_status,
                    leave_reason=EXCLUDED.leave_reason,
                    practice_duration=EXCLUDED.practice_duration,
                    attendance_note=EXCLUDED.attendance_note,
                    player_meals=EXCLUDED.player_meals,
                    parent_meals=EXCLUDED.parent_meals
            """, (
                event_id,body.player_id,body.attendance_status,
                body.leave_reason.strip(),body.practice_duration,
                body.attendance_note.strip(),
                player_meals,parent_meals
            ))

        conn.commit()

    return {"ok": True}


@app.get("/api/players/{player_id}/payments")
def player_payments(player_id: int, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM parent_players
                WHERE parent_id=%s AND player_id=%s
            """, (p["id"], player_id))

            if not cur.fetchone():
                raise HTTPException(403, "無權查看此球員")

            cur.execute("""
                SELECT id,player_id,title,amount,due_date::text,status,note
                FROM payments
                WHERE player_id=%s
                ORDER BY
                  CASE status WHEN 'unpaid' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                  due_date NULLS LAST
            """, (player_id,))
            return cur.fetchall()


# ---------------- Volunteer ----------------\n\n@app.get("/api/volunteers")\ndef parent_volunteers(authorization: str | None = Header(default=None)):\n    parent=current_parent(authorization)\n    with db() as conn:\n        with conn.cursor() as cur:\n            cur.execute("""\n                SELECT vs.id,vs.volunteer_date::text,vs.group_name,vs.capacity,vs.note,vs.status,\n                       COUNT(vsg.id) signup_count,\n                       EXISTS(SELECT 1 FROM volunteer_signups x WHERE x.slot_id=vs.id AND x.parent_id=%s) signed_by_me\n                FROM volunteer_slots vs\n                LEFT JOIN volunteer_signups vsg ON vsg.slot_id=vs.id\n                WHERE vs.volunteer_date >= %s\n                GROUP BY vs.id\n                ORDER BY vs.volunteer_date,vs.group_name\n            """,(parent["id"],date.today()))\n            slots=cur.fetchall()\n            cur.execute("""\n                SELECT p.id,p.name,p.team,p.number\n                FROM players p JOIN parent_players pp ON pp.player_id=p.id\n                WHERE pp.parent_id=%s AND p.active=TRUE\n                ORDER BY p.team,p.name\n            """,(parent["id"],))\n            players=cur.fetchall()\n    return {"slots":slots,"players":players}\n\n\n@app.post("/api/volunteers/{slot_id}/signup")\ndef volunteer_signup(slot_id:int,body:VolunteerSignupIn,authorization:str|None=Header(default=None)):\n    parent=current_parent(authorization)\n    with db() as conn:\n        with conn.cursor() as cur:\n            cur.execute("SELECT * FROM volunteer_slots WHERE id=%s FOR UPDATE",(slot_id,))\n            slot=cur.fetchone()\n            if not slot: raise HTTPException(404,"找不到義工時段")\n            if slot["volunteer_date"] < date.today(): raise HTTPException(400,"此日期已過")\n            if slot["status"] != "open": raise HTTPException(400,"此義工時段已關閉")\n            if body.player_id is not None:\n                cur.execute("SELECT 1 FROM parent_players WHERE parent_id=%s AND player_id=%s",(parent["id"],body.player_id))\n                if not cur.fetchone(): raise HTTPException(403,"無權使用此球員資料")\n            cur.execute("SELECT 1 FROM volunteer_signups WHERE slot_id=%s AND parent_id=%s",(slot_id,parent["id"]))\n            if cur.fetchone(): raise HTTPException(409,"你已經登記此時段")\n            cur.execute("SELECT COUNT(*) n FROM volunteer_signups WHERE slot_id=%s",(slot_id,))\n            if cur.fetchone()["n"] >= slot["capacity"]: raise HTTPException(409,"此義工時段已額滿")\n            cur.execute("INSERT INTO volunteer_signups(slot_id,parent_id,player_id) VALUES(%s,%s,%s)",(slot_id,parent["id"],body.player_id))\n        conn.commit()\n    return {"ok":True}\n\n\n@app.delete("/api/volunteers/{slot_id}/signup")\ndef cancel_volunteer_signup(slot_id:int,authorization:str|None=Header(default=None)):\n    parent=current_parent(authorization)\n    with db() as conn:\n        with conn.cursor() as cur:\n            cur.execute("DELETE FROM volunteer_signups WHERE slot_id=%s AND parent_id=%s",(slot_id,parent["id"]))\n        conn.commit()\n    return {"ok":True}\n\n\n@app.get("/api/admin/volunteers")\ndef admin_volunteers(authorization:str|None=Header(default=None)):\n    require_admin(authorization)\n    with db() as conn:\n        with conn.cursor() as cur:\n            cur.execute("""\n                SELECT vs.id,vs.volunteer_date::text,vs.group_name,vs.capacity,vs.note,vs.status,\n                       COUNT(vsg.id) signup_count,\n                       COALESCE(json_agg(json_build_object('parent_name',pa.display_name,'player_name',pl.name,'team',pl.team) ORDER BY pa.display_name)\n                         FILTER (WHERE vsg.id IS NOT NULL),'[]'::json) signups\n                FROM volunteer_slots vs\n                LEFT JOIN volunteer_signups vsg ON vsg.slot_id=vs.id\n                LEFT JOIN parents pa ON pa.id=vsg.parent_id\n                LEFT JOIN players pl ON pl.id=vsg.player_id\n                GROUP BY vs.id\n                ORDER BY vs.volunteer_date DESC,vs.group_name\n            """)\n            return cur.fetchall()\n\n\n@app.post("/api/admin/volunteers")\ndef create_volunteer_slots(body:VolunteerSlotIn,authorization:str|None=Header(default=None)):\n    require_admin(authorization)\n    groups=[g for g in body.groups if g in {"少棒","青少棒"}]\n    if not groups: raise HTTPException(400,"請至少選擇一個組別")\n    with db() as conn:\n        with conn.cursor() as cur:\n            for group in groups:\n                cur.execute("""\n                    INSERT INTO volunteer_slots(volunteer_date,group_name,capacity,note,status)\n                    VALUES(%s,%s,%s,%s,'open')\n                    ON CONFLICT(volunteer_date,group_name) DO UPDATE SET capacity=EXCLUDED.capacity,note=EXCLUDED.note\n                """,(body.volunteer_date,group,max(1,body.capacity),body.note.strip()))\n        conn.commit()\n    return {"ok":True}\n\n\n@app.put("/api/admin/volunteers/{slot_id}/status")\ndef volunteer_status(slot_id:int,status:str=Query(...),authorization:str|None=Header(default=None)):\n    require_admin(authorization)\n    if status not in ("open","closed"): raise HTTPException(400,"status 錯誤")\n    with db() as conn:\n        with conn.cursor() as cur:\n            cur.execute("UPDATE volunteer_slots SET status=%s WHERE id=%s RETURNING id",(status,slot_id))\n            row=cur.fetchone()\n        conn.commit()\n    if not row: raise HTTPException(404,"找不到義工時段")\n    return {"ok":True}\n\n\n@app.delete("/api/admin/volunteers/{slot_id}")\ndef delete_volunteer_slot(slot_id:int,authorization:str|None=Header(default=None)):\n    require_admin(authorization)\n    with db() as conn:\n        with conn.cursor() as cur:\n            cur.execute("DELETE FROM volunteer_slots WHERE id=%s RETURNING id",(slot_id,))\n            row=cur.fetchone()\n        conn.commit()\n    if not row: raise HTTPException(404,"找不到義工時段")\n    return {"ok":True}\n\n\n# ---------------- Admin auth ----------------

class VolunteerSignupIn(BaseModel):
    player_id: int | None = None


class VolunteerSlotIn(BaseModel):
    volunteer_date: str
    groups: list[str] = ["少棒", "青少棒"]
    capacity: int = 1
    note: str = ""


class AdminLogin(BaseModel):
    password: str


@app.post("/api/admin/login")
def admin_login(body: AdminLogin):
    if not secrets.compare_digest(body.password, ADMIN_PASSWORD):
        raise HTTPException(401, "管理員密碼錯誤")
    return {"token": f"admin:{ADMIN_PASSWORD}"}


def require_admin(authorization):
    if not authorization:
        raise HTTPException(401, "管理員驗證失敗")

    expected = f"Bearer admin:{ADMIN_PASSWORD}"
    if secrets.compare_digest(authorization, expected):
        return {"type": "password"}

    prefix = "Bearer parent-admin:"
    if authorization.startswith(prefix):
        try:
            parent_id = int(authorization[len(prefix):])
        except Exception:
            raise HTTPException(401, "管理員驗證失敗")

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id,display_name,line_user_id,is_admin
                    FROM parents
                    WHERE id=%s
                """, (parent_id,))
                parent = cur.fetchone()

        if parent and parent.get("is_admin", False):
            return {"type": "line", "parent": parent}

    raise HTTPException(401, "管理員驗證失敗")


# ---------------- Admin models ----------------

class PlayerIn(BaseModel):
    name: str
    team: str
    number: str = ""
    active: bool = True
    max_parents: int = 2


class ParentIn(BaseModel):
    display_name: str
    line_user_id: str
    phone: str = ""
    is_primary: bool = True


class BindIn(BaseModel):
    parent_id: int
    player_id: int


class MatchIn(BaseModel):
    game_time: str | None = None
    game_time_tbd: bool = False
    opponent: str = ""


class EventIn(BaseModel):
    title: str
    event_date: str
    location: str
    meal_enabled: bool = True
    meal_price: int = 0
    event_type: str = "practice"
    response_deadline: str | None = None
    meet_time: str | None = None
    meet_time_tbd: bool = False
    matches: list[MatchIn] = []
    player_ids: list[int] = []


class EventUpdateIn(EventIn):
    status: str = "open"


class PaymentIn(BaseModel):
    player_id: int
    title: str
    amount: int
    due_date: str | None = None
    status: str = "unpaid"
    note: str = ""


class PaymentBatchIn(BaseModel):
    target_type: str
    target_value: str | None = None
    target_values: list[str] = []
    title: str
    amount: int
    due_date: str | None = None
    status: str = "unpaid"
    note: str = ""


class NotifyIn(BaseModel):
    mode: str = "all"
    primary_only: bool = False


class AnnouncementUpdateIn(BaseModel):
    title: str = ""
    message_text: str
    target_type: str = "all"
    target_values: list[str] = []
    active: bool = True


class MessageSendIn(BaseModel):
    target_type: str = "all"
    announcement_title: str = ""
    save_as_announcement: bool = True

    target_values: list[str] = []
    message: str


# ---------------- Admin dashboard ----------------

@app.get("/api/admin/dashboard")
def admin_dashboard(authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM players WHERE active=TRUE")
            players = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) n FROM parents")
            parents = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) n FROM events WHERE event_date >= %s", (date.today(),))
            events = cur.fetchone()["n"]

            cur.execute("SELECT COALESCE(SUM(amount),0) total FROM payments WHERE status<>'paid'")
            unpaid = cur.fetchone()["total"]

            cur.execute("""
                SELECT COUNT(*) n
                FROM event_players ep
                JOIN events e ON e.id=ep.event_id
                LEFT JOIN attendance a ON a.event_id=ep.event_id AND a.player_id=ep.player_id
                WHERE e.event_date >= %s AND a.id IS NULL
            """, (date.today(),))
            pending = cur.fetchone()["n"]

            cur.execute("""
                SELECT COUNT(*) n
                FROM parents pa
                LEFT JOIN parent_players pp ON pp.parent_id=pa.id
                WHERE pp.parent_id IS NULL
            """)
            unbound = cur.fetchone()["n"]

    return {
        "players": players,
        "parents": parents,
        "events": events,
        "unpaid": unpaid,
        "pending_replies": pending,
        "unbound_parents": unbound,
    }


# ---------------- Admin players / parents ----------------

@app.get("/api/admin/players")
def admin_players(authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.*,
                  COALESCE(
                    json_agg(json_build_object('id',pa.id,'display_name',pa.display_name))
                    FILTER (WHERE pa.id IS NOT NULL),
                    '[]'
                  ) parents,
                  COUNT(pa.id) AS linked_parent_count
                FROM players p
                LEFT JOIN parent_players pp ON pp.player_id=p.id
                LEFT JOIN parents pa ON pa.id=pp.parent_id
                GROUP BY p.id
                ORDER BY p.team,p.name
            """)
            return cur.fetchall()


@app.post("/api/admin/players")
def create_player(body: PlayerIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            for _ in range(20):
                code = new_bind_code()
                try:
                    cur.execute("""
                        INSERT INTO players(name,team,number,active,bind_code,max_parents)
                        VALUES(%s,%s,%s,%s,%s,%s)
                        RETURNING *
                    """, (
                        body.name.strip(),body.team.strip(),body.number.strip(),
                        body.active,code,max(1,body.max_parents)
                    ))
                    row = cur.fetchone()
                    conn.commit()
                    return row
                except psycopg.errors.UniqueViolation:
                    conn.rollback()

    raise HTTPException(500, "無法產生綁定碼")


@app.put("/api/admin/players/{player_id}")
def update_player(player_id: int, body: PlayerIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE players
                SET name=%s,team=%s,number=%s,active=%s,max_parents=%s
                WHERE id=%s
                RETURNING *
            """, (
                body.name.strip(),body.team.strip(),body.number.strip(),
                body.active,max(1,body.max_parents),player_id
            ))
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(404, "找不到球員")

    return row


@app.post("/api/admin/players/{player_id}/reset-bind-code")
def reset_bind_code(player_id: int, authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        for _ in range(20):
            code = new_bind_code()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE players
                        SET bind_code=%s
                        WHERE id=%s
                        RETURNING id,name,team,number,bind_code
                    """, (code, player_id))
                    row = cur.fetchone()

                if not row:
                    raise HTTPException(404, "找不到球員")

                conn.commit()
                return row

            except psycopg.errors.UniqueViolation:
                conn.rollback()

    raise HTTPException(500, "無法產生新的綁定碼")


@app.get("/api/admin/parents")
def admin_parents(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pa.id,pa.line_user_id,pa.display_name,pa.picture_url,pa.phone,pa.is_primary,pa.is_admin,pa.last_login_at,
                       COALESCE((
                           SELECT json_agg(json_build_object('id',p.id,'name',p.name,'team',p.team,'number',p.number) ORDER BY p.team,p.name)
                           FROM parent_players pp JOIN players p ON p.id=pp.player_id
                           WHERE pp.parent_id=pa.id
                       ), '[]'::json) AS players
                FROM parents pa
                ORDER BY pa.display_name
            """)
            return cur.fetchall()


@app.post("/api/admin/parents")
def create_parent(body: ParentIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)

    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO parents(display_name,line_user_id,phone,is_primary)
                    VALUES(%s,%s,%s,%s)
                    RETURNING *
                """, (
                    body.display_name.strip(),body.line_user_id.strip(),
                    body.phone.strip(),body.is_primary
                ))
                row = cur.fetchone()
            conn.commit()

        return row

    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "此 LINE User ID 已存在")



@app.put("/api/admin/parents/{parent_id}/admin")
def set_parent_admin(
    parent_id: int,
    enabled: bool = Query(...),
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE parents
                SET is_admin=%s
                WHERE id=%s
                RETURNING id,display_name,line_user_id,is_admin
            """, (enabled, parent_id))
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(404, "找不到家長")

    return {"ok": True, "parent": row}


@app.post("/api/admin/bind")
def admin_bind(body: BindIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO parent_players(parent_id,player_id)
                VALUES(%s,%s)
                ON CONFLICT DO NOTHING
            """, (body.parent_id, body.player_id))
        conn.commit()

    return {"ok": True}


@app.delete("/api/admin/bind")
def admin_unbind(
    parent_id: int = Query(...),
    player_id: int = Query(...),
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM parent_players
                WHERE parent_id=%s AND player_id=%s
            """, (parent_id, player_id))
        conn.commit()

    return {"ok": True}


def normalize_time_value(value):
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    text = str(value)
    return text[:5] if len(text) >= 5 else text


def fetch_event_matches(cur, event_id):
    cur.execute("""
        SELECT id,event_id,match_order,game_time,game_time_tbd,opponent
        FROM event_matches
        WHERE event_id=%s
        ORDER BY match_order,id
    """, (event_id,))
    rows = cur.fetchall()
    for row in rows:
        row["game_time"] = normalize_time_value(row.get("game_time"))
    return rows


@app.delete("/api/admin/players/{player_id}")
def delete_player(player_id: int, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,name,team FROM players WHERE id=%s",(player_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(404,"找不到球員")
            cur.execute("DELETE FROM players WHERE id=%s",(player_id,))
        conn.commit()
    return {"ok":True,"deleted":row}


@app.delete("/api/admin/parents/{parent_id}")
def delete_parent(parent_id: int, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,display_name,line_user_id FROM parents WHERE id=%s",(parent_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(404,"找不到家長")
            cur.execute("DELETE FROM parents WHERE id=%s",(parent_id,))
        conn.commit()
    return {"ok":True,"deleted":row}


@app.delete("/api/admin/events/{event_id}")
def delete_event(event_id: int, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,title,event_date::text FROM events WHERE id=%s",(event_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(404,"找不到活動")
            cur.execute("DELETE FROM events WHERE id=%s",(event_id,))
        conn.commit()
    return {"ok":True,"deleted":row}


# ---------------- Admin events ----------------

@app.get("/api/admin/events")
def admin_events(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.id,e.title,e.event_date::text,e.location,e.meal_price,e.status,e.event_type,
                       e.response_deadline::text,e.meet_time,e.meet_time_tbd,
                       COUNT(ep.player_id) invited,COUNT(a.id) replied,
                       COALESCE(SUM(CASE WHEN a.attendance_status='attend' THEN 1 ELSE 0 END),0) attend,
                       COALESCE(SUM(CASE WHEN a.attendance_status='leave' THEN 1 ELSE 0 END),0) leave,
                       COALESCE(SUM(CASE WHEN a.attendance_status='maybe' THEN 1 ELSE 0 END),0) maybe,
                       COALESCE(SUM(COALESCE(a.player_meals,0)+COALESCE(a.parent_meals,0)),0) meals,
                       (SELECT COUNT(*) FROM event_matches em WHERE em.event_id=e.id) match_count
                FROM events e
                LEFT JOIN event_players ep ON ep.event_id=e.id
                LEFT JOIN attendance a ON a.event_id=e.id AND a.player_id=ep.player_id
                GROUP BY e.id
                ORDER BY e.event_date DESC,e.id DESC
            """)
            rows=cur.fetchall()
            for row in rows:
                row["meet_time"]=normalize_time_value(row.get("meet_time"))
            return rows


@app.post("/api/admin/events")
def create_event(body: EventIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO events(title,event_date,location,meal_price,event_type,response_deadline,meet_time,meet_time_tbd)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
            """,(body.title.strip(),body.event_date,body.location.strip(),body.meal_price,body.event_type,body.response_deadline or None,
                  None if body.meet_time_tbd else (body.meet_time or None),body.meet_time_tbd))
            event=cur.fetchone()
            if body.player_ids:
                cur.executemany("INSERT INTO event_players(event_id,player_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",[(event["id"],pid) for pid in body.player_ids])
            for idx,m in enumerate(body.matches,start=1):
                cur.execute("INSERT INTO event_matches(event_id,match_order,game_time,game_time_tbd,opponent) VALUES(%s,%s,%s,%s,%s)",
                            (event["id"],idx,None if m.game_time_tbd else (m.game_time or None),m.game_time_tbd,m.opponent.strip()))
        conn.commit()
    return event


@app.put("/api/admin/events/{event_id}")
def update_event(event_id: int, body: EventUpdateIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE events SET title=%s,event_date=%s,location=%s,meal_price=%s,event_type=%s,response_deadline=%s,status=%s,meet_time=%s,meet_time_tbd=%s
                WHERE id=%s RETURNING *
            """,(body.title.strip(),body.event_date,body.location.strip(),body.meal_price,body.event_type,body.response_deadline or None,body.status,
                  None if body.meet_time_tbd else (body.meet_time or None),body.meet_time_tbd,event_id))
            event=cur.fetchone()
            if not event: raise HTTPException(404,"找不到活動")
            cur.execute("DELETE FROM event_players WHERE event_id=%s",(event_id,))
            if body.player_ids:
                cur.executemany("INSERT INTO event_players(event_id,player_id) VALUES(%s,%s)",[(event_id,pid) for pid in body.player_ids])
            cur.execute("DELETE FROM event_matches WHERE event_id=%s",(event_id,))
            for idx,m in enumerate(body.matches,start=1):
                cur.execute("INSERT INTO event_matches(event_id,match_order,game_time,game_time_tbd,opponent) VALUES(%s,%s,%s,%s,%s)",
                            (event_id,idx,None if m.game_time_tbd else (m.game_time or None),m.game_time_tbd,m.opponent.strip()))
        conn.commit()
    return event


@app.get("/api/admin/events/{event_id}")
def admin_event_detail(event_id: int, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,title,event_date::text,location,meal_price,status,event_type,response_deadline::text,meet_time,meet_time_tbd FROM events WHERE id=%s",(event_id,))
            event=cur.fetchone()
            if not event: raise HTTPException(404,"找不到活動")
            event["meet_time"]=normalize_time_value(event.get("meet_time"))
            cur.execute("""
                SELECT p.id,p.name,p.team,p.number,a.attendance_status,a.leave_reason,
                       a.practice_duration,a.attendance_note,
                       COALESCE(a.player_meals,0) player_meals,COALESCE(a.parent_meals,0) parent_meals
                FROM event_players ep JOIN players p ON p.id=ep.player_id
                LEFT JOIN attendance a ON a.event_id=ep.event_id AND a.player_id=ep.player_id
                WHERE ep.event_id=%s ORDER BY p.team,p.name
            """,(event_id,))
            players=cur.fetchall()
            matches=fetch_event_matches(cur,event_id)
    return {"event":event,"players":players,"matches":matches}


# ---------------- Admin payments ----------------

@app.get("/api/admin/payments")
def admin_payments(authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pay.id,pay.player_id,p.name player_name,p.team,
                       pay.title,pay.amount,pay.due_date::text,pay.status,pay.note
                FROM payments pay
                JOIN players p ON p.id=pay.player_id
                ORDER BY
                  CASE pay.status WHEN 'unpaid' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                  pay.due_date NULLS LAST,p.name
            """)
            return cur.fetchall()


@app.post("/api/admin/payments")
def create_payment(body: PaymentIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO payments(
                    player_id,title,amount,due_date,status,note
                )
                VALUES(%s,%s,%s,%s,%s,%s)
                RETURNING *
            """, (
                body.player_id,body.title.strip(),body.amount,
                body.due_date or None,body.status,body.note.strip()
            ))
            row = cur.fetchone()
        conn.commit()

    return row



@app.post("/api/admin/payments/batch")
def create_payment_batch(
    body: PaymentBatchIn,
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)

    if body.target_type not in ("all", "team", "player"):
        raise HTTPException(400, "target_type 錯誤")

    if body.amount < 0:
        raise HTTPException(400, "金額不可為負數")

    if body.status not in ("unpaid", "pending", "paid"):
        raise HTTPException(400, "status 錯誤")

    with db() as conn:
        with conn.cursor() as cur:
            if body.target_type == "all":
                cur.execute("""
                    SELECT id,name,team
                    FROM players
                    WHERE active=TRUE
                    ORDER BY team,name
                """)
            elif body.target_type == "team":
                teams = body.target_values or ([body.target_value] if body.target_value else [])
                allowed_teams = {"U10", "U12", "U13", "U15"}
                teams = [t for t in teams if t in allowed_teams]

                if not teams:
                    raise HTTPException(400, "請至少選擇一個組別")

                cur.execute("""
                    SELECT id,name,team
                    FROM players
                    WHERE active=TRUE AND team = ANY(%s)
                    ORDER BY team,name
                """, (teams,))
            else:
                try:
                    player_id = int(body.target_value or "")
                except ValueError:
                    raise HTTPException(400, "球員 ID 錯誤")

                cur.execute("""
                    SELECT id,name,team
                    FROM players
                    WHERE active=TRUE AND id=%s
                """, (player_id,))

            players = cur.fetchall()

            if not players:
                raise HTTPException(404, "找不到符合條件的球員")

            rows = []
            for p in players:
                cur.execute("""
                    INSERT INTO payments(
                        player_id,title,amount,due_date,status,note
                    )
                    VALUES(%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """, (
                    p["id"],
                    body.title.strip(),
                    body.amount,
                    body.due_date or None,
                    body.status,
                    body.note.strip()
                ))
                new_row = cur.fetchone()
                rows.append({
                    "payment_id": new_row["id"],
                    "player_id": p["id"],
                    "player_name": p["name"],
                    "team": p["team"]
                })

        conn.commit()

    return {
        "ok": True,
        "created_count": len(rows),
        "payments": rows
    }


@app.put("/api/admin/payments/{payment_id}/status")
def update_payment_status(
    payment_id: int,
    status: str = Query(...),
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    if status not in ("unpaid", "paid", "pending"):
        raise HTTPException(400, "status 錯誤")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE payments
                SET status=%s
                WHERE id=%s
                RETURNING *
            """, (status, payment_id))
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(404, "找不到繳費項目")

    return row



@app.delete("/api/admin/payments/{payment_id}")
def delete_payment(
    payment_id: int,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    pay.id,
                    pay.title,
                    pay.amount,
                    p.name AS player_name,
                    p.team
                FROM payments pay
                JOIN players p ON p.id=pay.player_id
                WHERE pay.id=%s
            """, (payment_id,))
            payment = cur.fetchone()

            if not payment:
                raise HTTPException(404, "找不到繳費項目")

            cur.execute("""
                DELETE FROM payments
                WHERE id=%s
            """, (payment_id,))

        conn.commit()

    return {
        "ok": True,
        "deleted": {
            "id": payment["id"],
            "title": payment["title"],
            "amount": payment["amount"],
            "player_name": payment["player_name"],
            "team": payment["team"],
        }
    }




def verify_line_signature(raw_body: bytes, signature: str | None):
    if not LINE_CHANNEL_SECRET:
        raise HTTPException(503, "LINE_CHANNEL_SECRET 尚未設定")

    if not signature:
        raise HTTPException(400, "缺少 LINE Signature")

    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).digest()

    expected = base64.b64encode(digest).decode("utf-8")

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "LINE Signature 驗證失敗")


@app.post("/line/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None)
):
    raw_body = await request.body()
    verify_line_signature(raw_body, x_line_signature)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Webhook JSON 格式錯誤")

    events = payload.get("events", [])

    for event in events:
        event_type = event.get("type")
        source = event.get("source") or {}
        line_user_id = source.get("userId")

        if not line_user_id:
            continue

        # 收家長文字回覆
        if event_type == "message":
            message = event.get("message") or {}
            message_type = message.get("type", "unknown")
            message_text = message.get("text", "") if message_type == "text" else ""

            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM parents WHERE line_user_id=%s",
                        (line_user_id,)
                    )
                    parent = cur.fetchone()

                    cur.execute("""
                        INSERT INTO inbound_messages(
                            parent_id,line_user_id,message_type,message_text,is_read
                        )
                        VALUES(%s,%s,%s,%s,FALSE)
                    """, (
                        parent["id"] if parent else None,
                        line_user_id,
                        message_type,
                        message_text
                    ))
                conn.commit()

        # 家長加好友時不強制建立 parents；
        # 正式登入 LIFF 後會由 /api/auth/line 自動建立。
        elif event_type == "follow":
            pass

    return {"ok": True}



def save_app_announcement(
    message_text: str,
    target_type: str,
    target_values: list[str],
    title: str = "",
    source_key: str | None = None,
):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO announcements(
                    title,message_text,target_type,target_values,active,source_key
                )
                VALUES(%s,%s,%s,%s::jsonb,TRUE,%s)
                RETURNING id
            """, (
                title.strip(),
                message_text.strip(),
                target_type,
                json.dumps(target_values, ensure_ascii=False),
                source_key,
            ))
            row = cur.fetchone()
        conn.commit()
    return row["id"]


# ---------------- Admin message center ----------------

def resolve_message_recipients(cur, target_type: str, target_values: list[str]):
    if target_type == "all":
        cur.execute("""
            SELECT DISTINCT pa.id,pa.line_user_id,pa.display_name
            FROM parents pa
            WHERE pa.line_user_id IS NOT NULL
              AND BTRIM(pa.line_user_id) <> ''
            ORDER BY pa.display_name
        """)
        return cur.fetchall(), "全部家長"

    if target_type == "team":
        allowed = {"U10", "U12", "U13", "U15"}
        teams = [x for x in target_values if x in allowed]
        if not teams:
            raise HTTPException(400, "請至少選擇一個組別")

        cur.execute("""
            SELECT DISTINCT pa.id,pa.line_user_id,pa.display_name
            FROM parents pa
            JOIN parent_players pp ON pp.parent_id=pa.id
            JOIN players p ON p.id=pp.player_id
            WHERE p.active=TRUE
              AND p.team = ANY(%s)
              AND pa.line_user_id IS NOT NULL
              AND BTRIM(pa.line_user_id) <> ''
            ORDER BY pa.display_name
        """, (teams,))
        return cur.fetchall(), "、".join(teams)

    if target_type == "parent":
        parent_ids = []
        for value in target_values:
            try:
                parent_ids.append(int(value))
            except (TypeError, ValueError):
                pass
        if not parent_ids:
            raise HTTPException(400, "請至少選擇一位家長")

        cur.execute("""
            SELECT DISTINCT id,line_user_id,display_name
            FROM parents
            WHERE id = ANY(%s)
              AND line_user_id IS NOT NULL
              AND BTRIM(line_user_id) <> ''
            ORDER BY display_name
        """, (parent_ids,))
        return cur.fetchall(), "指定家長"

    raise HTTPException(400, "target_type 錯誤")


@app.get("/api/admin/messages/preview")
def preview_message_targets(
    target_type: str = Query("all"),
    target_values: str = Query(""),
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)
    values = [x for x in target_values.split(",") if x]
    with db() as conn:
        with conn.cursor() as cur:
            recipients, label = resolve_message_recipients(cur, target_type, values)

    return {
        "target_type": target_type,
        "target_label": label,
        "recipient_count": len(recipients),
        "recipients": [
            {"id": r["id"], "display_name": r["display_name"]}
            for r in recipients
        ],
    }


async def push_text_message(user_id: str, message: str):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return False, "LINE_CHANNEL_ACCESS_TOKEN 尚未設定"

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"to": user_id, "messages": [{"type": "text", "text": message}]},
        )

    if 200 <= r.status_code < 300:
        return True, ""
    return False, f"HTTP {r.status_code}: {r.text[:300]}"



@app.get("/api/admin/line/quota")
def admin_line_quota(
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)

    if not LINE_CHANNEL_ACCESS_TOKEN:
        raise HTTPException(503, "尚未設定 LINE_CHANNEL_ACCESS_TOKEN")

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }

    try:
        quota_resp = httpx.get(
            "https://api.line.me/v2/bot/message/quota",
            headers=headers,
            timeout=10,
        )
        usage_resp = httpx.get(
            "https://api.line.me/v2/bot/message/quota/consumption",
            headers=headers,
            timeout=10,
        )
    except httpx.RequestError as e:
        raise HTTPException(502, f"無法連線 LINE Messaging API：{e}")

    if quota_resp.status_code != 200:
        raise HTTPException(
            quota_resp.status_code,
            f"LINE 額度查詢失敗：{quota_resp.text}"
        )

    if usage_resp.status_code != 200:
        raise HTTPException(
            usage_resp.status_code,
            f"LINE 用量查詢失敗：{usage_resp.text}"
        )

    quota = quota_resp.json()
    usage = usage_resp.json()

    quota_type = quota.get("type", "none")
    limit_value = quota.get("value") if quota_type == "limited" else None
    total_usage = int(usage.get("totalUsage", 0) or 0)

    remaining = None
    percent = None
    if limit_value is not None:
        limit_value = int(limit_value)
        remaining = max(limit_value - total_usage, 0)
        percent = round((total_usage / limit_value) * 100, 1) if limit_value else 0

    return {
        "type": quota_type,
        "limit": limit_value,
        "usage": total_usage,
        "remaining": remaining,
        "percent": percent,
    }


@app.post("/api/admin/messages/send")
async def send_admin_message(
    body: MessageSendIn,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    message = body.message.strip()
    if not message:
        raise HTTPException(400, "訊息內容不可空白")
    if len(message) > 5000:
        raise HTTPException(400, "訊息內容過長")

    with db() as conn:
        with conn.cursor() as cur:
            recipients, label = resolve_message_recipients(
                cur, body.target_type, body.target_values
            )

    if not recipients:
        raise HTTPException(404, "沒有符合條件的家長")

    # LINE 群發紀錄與 App 公告共用同一個 batch/source key
    batch_id = secrets.token_hex(12)

    announcement_id = None
    if body.save_as_announcement:
        announcement_id = save_app_announcement(
            message_text=message,
            target_type=body.target_type,
            target_values=body.target_values,
            title=body.announcement_title,
            source_key="batch:" + batch_id,
        )

    results = []

    for recipient in recipients:
        ok, error = await push_text_message(recipient["line_user_id"], message)
        results.append({
            "parent_id": recipient["id"],
            "display_name": recipient["display_name"],
            "ok": ok,
            "error": error,
        })

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO message_logs(
                        parent_id,line_user_id,recipient_name,
                        target_type,target_label,message_text,
                        status,error_message,batch_id
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    recipient["id"],
                    recipient["line_user_id"],
                    recipient["display_name"],
                    body.target_type,
                    label,
                    message,
                    "sent" if ok else "failed",
                    error,
                    batch_id,
                ))
            conn.commit()

    return {
        "ok": all(x["ok"] for x in results),
        "recipient_count": len(recipients),
        "sent": sum(1 for x in results if x["ok"]),
        "failed": sum(1 for x in results if not x["ok"]),
        "results": results,
        "announcement_id": announcement_id,
    }


@app.get("/api/admin/messages/logs")
def admin_message_logs(
    limit: int = Query(50, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH source AS (
                    SELECT
                        CASE
                            WHEN batch_id IS NOT NULL AND BTRIM(batch_id) <> ''
                                THEN 'batch:' || batch_id
                            ELSE
                                'legacy:' ||
                                TO_CHAR(sent_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD') ||
                                ':' || COALESCE(target_type,'') ||
                                ':' || COALESCE(target_label,'') ||
                                ':' || MD5(COALESCE(message_text,''))
                        END AS group_id,
                        sent_at,
                        target_type,
                        target_label,
                        message_text,
                        status
                    FROM message_logs
                    WHERE NOT (
                        target_type='parent'
                        AND target_label='單一家長'
                    )
                ),
                grouped AS (
                    SELECT
                        group_id,
                        MIN(sent_at) AS sent_at,
                        MAX(target_type) AS target_type,
                        MAX(target_label) AS target_label,
                        MAX(message_text) AS message_text,
                        COUNT(*) AS recipient_count,
                        COUNT(*) FILTER (WHERE status='sent') AS sent_count,
                        COUNT(*) FILTER (WHERE status='failed') AS failed_count
                    FROM source
                    GROUP BY group_id
                )
                SELECT
                    group_id,
                    sent_at,
                    target_type,
                    target_label,
                    message_text,
                    recipient_count,
                    sent_count,
                    failed_count
                FROM grouped
                ORDER BY sent_at DESC
                LIMIT %s
            """, (limit,))

            return cur.fetchall()


@app.get("/api/admin/messages/conversations")
def admin_message_conversations(
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH inbound AS (
                    SELECT
                        im.line_user_id,
                        MAX(im.received_at) AS last_inbound_at,
                        COUNT(*) FILTER (WHERE im.is_read=FALSE) AS unread_count
                    FROM inbound_messages im
                    GROUP BY im.line_user_id
                ),
                outbound AS (
                    SELECT
                        ml.line_user_id,
                        MAX(ml.sent_at) AS last_outbound_at
                    FROM message_logs ml
                    GROUP BY ml.line_user_id
                ),
                ids AS (
                    SELECT line_user_id FROM inbound
                    UNION
                    SELECT line_user_id FROM outbound
                )
                SELECT
                    ids.line_user_id,
                    pa.id AS parent_id,
                    COALESCE(pa.display_name,'未登錄 LINE 使用者') AS display_name,
                    COALESCE(i.unread_count,0) AS unread_count,
                    GREATEST(
                        COALESCE(i.last_inbound_at, to_timestamp(0)),
                        COALESCE(o.last_outbound_at, to_timestamp(0))
                    ) AS last_message_at,
                    COALESCE(
                        (
                            SELECT json_agg(
                                json_build_object(
                                    'id',p.id,
                                    'name',p.name,
                                    'team',p.team
                                )
                                ORDER BY p.team,p.name
                            )
                            FROM parent_players pp
                            JOIN players p ON p.id=pp.player_id
                            WHERE pp.parent_id=pa.id
                        ),
                        '[]'::json
                    ) AS players
                FROM ids
                LEFT JOIN parents pa ON pa.line_user_id=ids.line_user_id
                LEFT JOIN inbound i ON i.line_user_id=ids.line_user_id
                LEFT JOIN outbound o ON o.line_user_id=ids.line_user_id
                ORDER BY unread_count DESC,last_message_at DESC
            """)
            return cur.fetchall()


@app.get("/api/admin/messages/conversation/{line_user_id}")
def admin_message_conversation(
    line_user_id: str,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,display_name
                FROM parents
                WHERE line_user_id=%s
            """, (line_user_id,))
            parent = cur.fetchone()

            cur.execute("""
                SELECT *
                FROM (
                    SELECT
                        im.id,
                        'in' AS direction,
                        im.message_text AS message_text,
                        im.message_type AS message_type,
                        im.received_at AS message_at,
                        im.is_read AS is_read,
                        '' AS status,
                        '' AS error_message
                    FROM inbound_messages im
                    WHERE im.line_user_id=%s

                    UNION ALL

                    SELECT
                        ml.id,
                        'out' AS direction,
                        ml.message_text AS message_text,
                        'text' AS message_type,
                        ml.sent_at AS message_at,
                        TRUE AS is_read,
                        ml.status AS status,
                        ml.error_message AS error_message
                    FROM message_logs ml
                    WHERE ml.line_user_id=%s
                ) x
                ORDER BY message_at,id
            """, (line_user_id,line_user_id))
            messages = cur.fetchall()

            cur.execute("""
                SELECT p.id,p.name,p.team
                FROM parent_players pp
                JOIN players p ON p.id=pp.player_id
                JOIN parents pa ON pa.id=pp.parent_id
                WHERE pa.line_user_id=%s
                ORDER BY p.team,p.name
            """, (line_user_id,))
            players = cur.fetchall()

    return {
        "line_user_id": line_user_id,
        "parent": parent,
        "players": players,
        "messages": messages,
    }


@app.post("/api/admin/messages/conversation/{line_user_id}/read")
def mark_admin_conversation_read(
    line_user_id: str,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE inbound_messages
                SET is_read=TRUE
                WHERE line_user_id=%s
                  AND is_read=FALSE
            """, (line_user_id,))
        conn.commit()

    return {"ok": True}


class DirectReplyIn(BaseModel):
    message: str


@app.post("/api/admin/messages/conversation/{line_user_id}/reply")
async def reply_admin_conversation(
    line_user_id: str,
    body: DirectReplyIn,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    message = body.message.strip()
    if not message:
        raise HTTPException(400, "訊息內容不可空白")
    if len(message) > 5000:
        raise HTTPException(400, "訊息內容過長")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,display_name
                FROM parents
                WHERE line_user_id=%s
            """, (line_user_id,))
            parent = cur.fetchone()

    ok, error = await push_text_message(line_user_id, message)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO message_logs(
                    parent_id,line_user_id,recipient_name,
                    target_type,target_label,message_text,
                    status,error_message,batch_id
                )
                VALUES(%s,%s,%s,'parent','單一家長',%s,%s,%s,%s)
            """, (
                parent["id"] if parent else None,
                line_user_id,
                parent["display_name"] if parent else "未登錄 LINE 使用者",
                message,
                "sent" if ok else "failed",
                error,
                secrets.token_hex(12)
            ))
        conn.commit()

    if not ok:
        raise HTTPException(502, error)

    return {"ok": True}



@app.get("/api/admin/announcements/diagnostics")
def announcement_diagnostics(
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM announcements")
            announcements_count = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) n FROM message_logs")
            message_logs_count = cur.fetchone()["n"]

            cur.execute("""
                SELECT target_type,COUNT(*) n
                FROM message_logs
                GROUP BY target_type
                ORDER BY target_type
            """)
            message_types = cur.fetchall()

    return {
        "announcements": announcements_count,
        "message_logs": message_logs_count,
        "message_types": message_types,
    }


@app.get("/api/admin/announcements")
def admin_announcements(
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,title,message_text,target_type,target_values,
                       active,created_at
                FROM announcements
                ORDER BY created_at DESC,id DESC
                LIMIT 200
            """)
            return cur.fetchall()


@app.put("/api/admin/announcements/{announcement_id}")
def edit_announcement(
    announcement_id: int,
    body: AnnouncementUpdateIn,
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)

    message_text = body.message_text.strip()
    if not message_text:
        raise HTTPException(400, "公告內容不可空白")

    allowed_types = {"all", "team", "parent"}
    if body.target_type not in allowed_types:
        raise HTTPException(400, "公告對象格式錯誤")

    target_values = [str(x).strip() for x in body.target_values if str(x).strip()]

    if body.target_type == "team":
        allowed_teams = {"U10", "U12", "U13", "U15"}
        target_values = [x for x in target_values if x in allowed_teams]
        if not target_values:
            raise HTTPException(400, "請至少選擇一個組別")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE announcements
                SET title=%s,
                    message_text=%s,
                    target_type=%s,
                    target_values=%s::jsonb,
                    active=%s
                WHERE id=%s
                RETURNING id
            """, (
                body.title.strip(),
                message_text,
                body.target_type,
                json.dumps(target_values, ensure_ascii=False),
                body.active,
                announcement_id,
            ))
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(404, "找不到公告")

    return {"ok": True, "id": row["id"]}


@app.put("/api/admin/announcements/{announcement_id}/active")
def update_announcement_active(
    announcement_id: int,
    active: bool = Query(...),
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE announcements
                SET active=%s
                WHERE id=%s
                RETURNING id
            """, (active, announcement_id))
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(404, "找不到公告")
    return {"ok": True}


@app.delete("/api/admin/announcements/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM announcements
                WHERE id=%s
                RETURNING id
            """, (announcement_id,))
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(404, "找不到公告")
    return {"ok": True}


# ---------------- LINE notification ----------------

def notification_targets(event_id: int, mode: str = "all", primary_only: bool = False):
    if mode not in ("all", "unanswered"):
        raise HTTPException(400, "mode 錯誤")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.id,e.title,e.event_date::text,e.location,
                       e.response_deadline::text,e.event_type,e.meet_time,e.meet_time_tbd
                FROM events e
                WHERE e.id=%s
            """, (event_id,))
            event = cur.fetchone()

            if not event:
                raise HTTPException(404, "找不到活動")

            sql = """
                SELECT DISTINCT
                  p.id player_id,p.name player_name,p.team,
                  pa.id parent_id,pa.display_name parent_name,
                  pa.line_user_id,pa.is_primary,a.attendance_status
                FROM event_players ep
                JOIN players p ON p.id=ep.player_id
                LEFT JOIN attendance a
                  ON a.event_id=ep.event_id AND a.player_id=ep.player_id
                LEFT JOIN parent_players pp ON pp.player_id=p.id
                LEFT JOIN parents pa ON pa.id=pp.parent_id
                WHERE ep.event_id=%s
            """

            if mode == "unanswered":
                sql += " AND a.id IS NULL"

            if primary_only:
                sql += " AND pa.is_primary=TRUE"

            sql += " ORDER BY p.team,p.name,pa.display_name"

            cur.execute(sql, (event_id,))
            rows = cur.fetchall()
            event["meet_time"] = normalize_time_value(event.get("meet_time"))
            event["matches"] = fetch_event_matches(cur,event_id)

    return event, rows


@app.get("/api/admin/events/{event_id}/notification-targets")
def get_notification_targets(
    event_id: int,
    mode: str = Query("all"),
    primary_only: bool = Query(False),
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    event, rows = notification_targets(event_id, mode, primary_only)

    grouped = {}
    missing = []

    for r in rows:
        if not r["parent_id"] or not r["line_user_id"]:
            missing.append(r)
            continue

        key = r["line_user_id"]

        if key not in grouped:
            grouped[key] = {
                "line_user_id": key,
                "parent_id": r["parent_id"],
                "parent_name": r["parent_name"],
                "players": [],
            }

        grouped[key]["players"].append({
            "id": r["player_id"],
            "name": r["player_name"],
            "team": r["team"],
        })

    return {
        "event": event,
        "mode": mode,
        "recipients": list(grouped.values()),
        "recipient_count": len(grouped),
        "missing": missing,
        "missing_count": len(missing),
    }


async def push_line(user_id,event,player_names,reminder):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return False,"LINE_CHANNEL_ACCESS_TOKEN 尚未設定"
    title="⏰ 比賽調查提醒" if reminder else "⚾ 比賽參加調查"
    players="、".join(player_names)
    deadline=event.get("response_deadline") or "未設定"
    meet="未定" if event.get("meet_time_tbd") else (event.get("meet_time") or "未定")
    url=f"{APP_BASE_URL}/?event={event['id']}" if APP_BASE_URL else ""
    lines=[title,"",event["title"],f"日期：{event['event_date']}",f"集合時間：{meet}",f"地點：{event['location']}"]
    for idx,m in enumerate(event.get("matches") or [],start=1):
        game_time="未定" if m.get("game_time_tbd") else (m.get("game_time") or "未定")
        lines += ["",f"第{idx}場",f"比賽時間：{game_time}",f"對戰對手：{m.get('opponent') or '未定'}"]
    lines += ["",f"球員：{players}",f"回覆截止：{deadline}"]
    if reminder: lines += ["","目前尚未完成回覆，請協助填寫。"]
    if url: lines += ["",f"前往填寫：{url}"]
    text="\n".join(lines)
    async with httpx.AsyncClient(timeout=15) as client:
        r=await client.post("https://api.line.me/v2/bot/message/push",headers={"Authorization":f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}","Content-Type":"application/json"},json={"to":user_id,"messages":[{"type":"text","text":text}]})
    if 200 <= r.status_code < 300: return True,""
    return False,f"HTTP {r.status_code}: {r.text[:300]}"


@app.post("/api/admin/events/{event_id}/notify")
async def notify_event(
    event_id: int,
    body: NotifyIn,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)

    event, rows = notification_targets(event_id, body.mode, body.primary_only)
    grouped = {}

    for r in rows:
        if not r["parent_id"] or not r["line_user_id"]:
            continue

        key = r["line_user_id"]

        if key not in grouped:
            grouped[key] = {
                "parent_id": r["parent_id"],
                "parent_name": r["parent_name"],
                "line_user_id": key,
                "players": [],
            }

        grouped[key]["players"].append({
            "id": r["player_id"],
            "name": r["player_name"],
        })

    reminder = body.mode == "unanswered"
    results = []

    for recipient in grouped.values():
        ok, error = await push_line(
            recipient["line_user_id"],
            event,
            [p["name"] for p in recipient["players"]],
            reminder,
        )

        results.append({
            "parent_name": recipient["parent_name"],
            "ok": ok,
            "error": error,
        })

        with db() as conn:
            with conn.cursor() as cur:
                for p in recipient["players"]:
                    cur.execute("""
                        INSERT INTO notification_logs(
                          event_id,parent_id,player_id,notification_type,
                          line_user_id,status,error_message
                        )
                        VALUES(%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        event_id,
                        recipient["parent_id"],
                        p["id"],
                        "reminder" if reminder else "invite",
                        recipient["line_user_id"],
                        "sent" if ok else "failed",
                        error,
                    ))
            conn.commit()

    return {
        "sent": sum(1 for x in results if x["ok"]),
        "failed": sum(1 for x in results if not x["ok"]),
        "results": results,
    }


@app.get("/api/admin/events/{event_id}/notification-logs")
def notification_log(event_id: int, authorization: str | None = Header(default=None)):
    require_admin(authorization)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT nl.id,nl.notification_type,nl.status,nl.error_message,
                       nl.sent_at,pa.display_name parent_name,p.name player_name
                FROM notification_logs nl
                LEFT JOIN parents pa ON pa.id=nl.parent_id
                LEFT JOIN players p ON p.id=nl.player_id
                WHERE nl.event_id=%s
                ORDER BY nl.sent_at DESC
                LIMIT 100
            """, (event_id,))
            return cur.fetchall()
