
import os
from datetime import date

import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MOCK_LOGIN = os.getenv("MOCK_LOGIN", "1") == "1"

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 尚未設定。請填入 Supabase PostgreSQL connection string。")

app = FastAPI(title="球隊家長 App")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


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

            cur.execute("SELECT COUNT(*) AS n FROM parents")
            count = cur.fetchone()["n"]
            if count == 0 and MOCK_LOGIN:
                cur.execute(
                    "INSERT INTO parents(line_user_id, display_name) VALUES(%s,%s) RETURNING id",
                    ("mock-parent-001", "測試家長")
                )
                parent_id = cur.fetchone()["id"]

                cur.execute("INSERT INTO players(name, team) VALUES(%s,%s) RETURNING id", ("陳小明", "U12"))
                p1 = cur.fetchone()["id"]
                cur.execute("INSERT INTO players(name, team) VALUES(%s,%s) RETURNING id", ("陳小虎", "U10"))
                p2 = cur.fetchone()["id"]

                cur.executemany(
                    "INSERT INTO parent_players(parent_id, player_id) VALUES(%s,%s)",
                    [(parent_id, p1), (parent_id, p2)]
                )

                cur.executemany(
                    "INSERT INTO events(title,event_date,location,meal_price) VALUES(%s,%s,%s,%s)",
                    [
                        ("週六例行練球", "2026-09-05", "新湖慢壘球場", 100),
                        ("U12 秋季聯賽", "2026-09-12", "新竹棒球場", 100),
                        ("週六例行練球", "2026-09-19", "新湖慢壘球場", 100),
                    ]
                )

                cur.executemany(
                    "INSERT INTO payments(player_id,title,amount,due_date,status) VALUES(%s,%s,%s,%s,%s)",
                    [
                        (p1, "9 月隊費", 1500, "2026-09-10", "unpaid"),
                        (p1, "U12 秋季聯賽報名費", 800, "2026-09-05", "paid"),
                        (p2, "9 月隊費", 1500, "2026-09-10", "unpaid"),
                    ]
                )
        conn.commit()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def home():
    return FileResponse(os.path.join(BASE, "static", "index.html"))


class LineAuth(BaseModel):
    access_token: str | None = None


@app.post("/api/auth/line")
async def auth_line(payload: LineAuth):
    if MOCK_LOGIN and (not payload.access_token or payload.access_token == "mock"):
        profile = {
            "userId": "mock-parent-001",
            "displayName": "測試家長",
            "pictureUrl": ""
        }
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

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM parents WHERE line_user_id=%s", (profile["userId"],))
            row = cur.fetchone()

            if not row:
                if MOCK_LOGIN:
                    cur.execute(
                        "INSERT INTO parents(line_user_id,display_name,picture_url) VALUES(%s,%s,%s) RETURNING *",
                        (profile["userId"], profile.get("displayName", "家長"), profile.get("pictureUrl", ""))
                    )
                    row = cur.fetchone()
                else:
                    raise HTTPException(403, "此 LINE 帳號尚未綁定球隊家長")

            cur.execute(
                "UPDATE parents SET display_name=%s, picture_url=%s WHERE id=%s RETURNING *",
                (profile.get("displayName", row["display_name"]), profile.get("pictureUrl", ""), row["id"])
            )
            result = cur.fetchone()
        conn.commit()

    return {"token": f"parent:{result['id']}", "parent": result}


def current_parent(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer parent:"):
        raise HTTPException(401, "尚未登入")
    try:
        pid = int(authorization.split(":")[-1])
    except Exception:
        raise HTTPException(401, "登入資訊錯誤")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM parents WHERE id=%s", (pid,))
            p = cur.fetchone()
    if not p:
        raise HTTPException(401, "家長不存在")
    return p


@app.get("/api/me")
def me(authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT players.* FROM players
                JOIN parent_players pp ON pp.player_id=players.id
                WHERE pp.parent_id=%s ORDER BY players.name
            """, (p["id"],))
            players = cur.fetchall()
    return {"parent": p, "players": players}


@app.get("/api/events")
def events(authorization: str | None = Header(default=None)):
    current_parent(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,title,event_date::text,location,meal_price,status
                FROM events
                WHERE event_date >= %s
                ORDER BY event_date
            """, (date.today(),))
            rows = cur.fetchall()
    return rows


@app.get("/api/players/{player_id}/attendance")
def player_attendance(player_id: int, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM parent_players WHERE parent_id=%s AND player_id=%s",
                (p["id"], player_id)
            )
            owns = cur.fetchone()
            if not owns:
                raise HTTPException(403, "無權查看此球員")
            cur.execute("SELECT * FROM attendance WHERE player_id=%s", (player_id,))
            rows = cur.fetchall()
    return rows


class AttendanceIn(BaseModel):
    player_id: int
    attendance_status: str
    leave_reason: str = ""
    player_meals: int = 0
    parent_meals: int = 0


@app.put("/api/events/{event_id}/attendance")
def save_attendance(event_id: int, body: AttendanceIn, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    if body.attendance_status not in ("attend", "leave"):
        raise HTTPException(400, "attendance_status 必須是 attend 或 leave")
    if body.player_meals < 0 or body.parent_meals < 0:
        raise HTTPException(400, "餐點數量不可為負數")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM parent_players WHERE parent_id=%s AND player_id=%s",
                (p["id"], body.player_id)
            )
            if not cur.fetchone():
                raise HTTPException(403, "無權修改此球員")

            cur.execute("SELECT * FROM events WHERE id=%s AND status='open'", (event_id,))
            if not cur.fetchone():
                raise HTTPException(404, "活動不存在或已截止")

            cur.execute("""
                INSERT INTO attendance(event_id,player_id,attendance_status,leave_reason,player_meals,parent_meals)
                VALUES(%s,%s,%s,%s,%s,%s)
                ON CONFLICT(event_id,player_id) DO UPDATE SET
                    attendance_status=EXCLUDED.attendance_status,
                    leave_reason=EXCLUDED.leave_reason,
                    player_meals=EXCLUDED.player_meals,
                    parent_meals=EXCLUDED.parent_meals
            """, (
                event_id, body.player_id, body.attendance_status, body.leave_reason.strip(),
                body.player_meals, body.parent_meals
            ))
        conn.commit()
    return {"ok": True}


@app.get("/api/players/{player_id}/payments")
def payments(player_id: int, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM parent_players WHERE parent_id=%s AND player_id=%s",
                (p["id"], player_id)
            )
            if not cur.fetchone():
                raise HTTPException(403, "無權查看此球員")

            cur.execute("""
                SELECT id,player_id,title,amount,due_date::text,status,note
                FROM payments
                WHERE player_id=%s
                ORDER BY status DESC, due_date
            """, (player_id,))
            rows = cur.fetchall()
    return rows
