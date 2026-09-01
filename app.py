
import os
import secrets
from datetime import date

import httpx
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MOCK_LOGIN = os.getenv("MOCK_LOGIN", "1") == "1"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-now")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 尚未設定。")

app = FastAPI(title="球隊家長 App")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with db() as conn:
        with conn.cursor() as cur:
            # Base tables
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

            # Safe migrations for existing database
            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT ''")
            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT TRUE")
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS number TEXT DEFAULT ''")
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE")
            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'practice'")
            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS response_deadline DATE")

            cur.execute("""
            CREATE TABLE IF NOT EXISTS event_players (
                event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                PRIMARY KEY(event_id, player_id)
            )
            """)

            # Backfill existing events to all active players once, so old demo events stay visible.
            cur.execute("""
                INSERT INTO event_players(event_id, player_id)
                SELECT e.id, p.id
                FROM events e
                CROSS JOIN players p
                WHERE p.active = TRUE
                ON CONFLICT DO NOTHING
            """)

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


# ---------------- Parent auth ----------------

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

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM parents WHERE line_user_id=%s", (profile["userId"],))
            row = cur.fetchone()

            if not row:
                if not MOCK_LOGIN:
                    raise HTTPException(403, "此 LINE 帳號尚未綁定球隊家長")
                cur.execute(
                    "INSERT INTO parents(line_user_id,display_name,picture_url) VALUES(%s,%s,%s) RETURNING *",
                    (profile["userId"], profile.get("displayName", "家長"), profile.get("pictureUrl", ""))
                )
                row = cur.fetchone()

            cur.execute("""
                UPDATE parents SET display_name=%s, picture_url=%s
                WHERE id=%s RETURNING *
            """, (
                profile.get("displayName", row["display_name"]),
                profile.get("pictureUrl", ""),
                row["id"]
            ))
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
            row = cur.fetchone()
    if not row:
        raise HTTPException(401, "家長不存在")
    return row


# ---------------- Admin auth ----------------

class AdminLogin(BaseModel):
    password: str


@app.post("/api/admin/login")
def admin_login(body: AdminLogin):
    if not secrets.compare_digest(body.password, ADMIN_PASSWORD):
        raise HTTPException(401, "管理員密碼錯誤")
    return {"token": f"admin:{ADMIN_PASSWORD}"}


def require_admin(authorization: str | None):
    expected = f"Bearer admin:{ADMIN_PASSWORD}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "管理員驗證失敗")


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
                ORDER BY pl.team, pl.name
            """, (p["id"],))
            players = cur.fetchall()
    return {"parent": p, "players": players}


@app.get("/api/events")
def parent_events(authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT e.id,e.title,e.event_date::text,e.location,e.meal_price,
                                e.status,e.event_type,e.response_deadline::text
                FROM events e
                JOIN event_players ep ON ep.event_id=e.id
                JOIN parent_players pp ON pp.player_id=ep.player_id
                WHERE pp.parent_id=%s AND e.event_date >= %s
                ORDER BY e.event_date
            """, (p["id"], date.today()))
            return cur.fetchall()


@app.get("/api/players/{player_id}/attendance")
def player_attendance(player_id: int, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM parent_players WHERE parent_id=%s AND player_id=%s", (p["id"], player_id))
            if not cur.fetchone():
                raise HTTPException(403, "無權查看此球員")
            cur.execute("SELECT * FROM attendance WHERE player_id=%s", (player_id,))
            return cur.fetchall()


class AttendanceIn(BaseModel):
    player_id: int
    attendance_status: str
    leave_reason: str = ""
    player_meals: int = 0
    parent_meals: int = 0


@app.put("/api/events/{event_id}/attendance")
def save_attendance(event_id: int, body: AttendanceIn, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    if body.attendance_status not in ("attend", "leave", "maybe"):
        raise HTTPException(400, "attendance_status 錯誤")
    if body.player_meals < 0 or body.parent_meals < 0:
        raise HTTPException(400, "餐點數量不可為負數")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM parent_players WHERE parent_id=%s AND player_id=%s", (p["id"], body.player_id))
            if not cur.fetchone():
                raise HTTPException(403, "無權修改此球員")

            cur.execute("SELECT 1 FROM event_players WHERE event_id=%s AND player_id=%s", (event_id, body.player_id))
            if not cur.fetchone():
                raise HTTPException(403, "此球員不在本活動名單")

            cur.execute("""
                SELECT 1 FROM events
                WHERE id=%s AND status='open'
                  AND (response_deadline IS NULL OR response_deadline >= %s)
            """, (event_id, date.today()))
            if not cur.fetchone():
                raise HTTPException(403, "活動已截止")

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
def player_payments(player_id: int, authorization: str | None = Header(default=None)):
    p = current_parent(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM parent_players WHERE parent_id=%s AND player_id=%s", (p["id"], player_id))
            if not cur.fetchone():
                raise HTTPException(403, "無權查看此球員")
            cur.execute("""
                SELECT id,player_id,title,amount,due_date::text,status,note
                FROM payments WHERE player_id=%s
                ORDER BY CASE status WHEN 'unpaid' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                         due_date NULLS LAST
            """, (player_id,))
            return cur.fetchall()


# ---------------- Admin models ----------------

class PlayerIn(BaseModel):
    name: str
    team: str
    number: str = ""
    active: bool = True


class ParentIn(BaseModel):
    display_name: str
    line_user_id: str
    phone: str = ""
    is_primary: bool = True


class BindIn(BaseModel):
    parent_id: int
    player_id: int


class EventIn(BaseModel):
    title: str
    event_date: str
    location: str
    meal_price: int = 0
    event_type: str = "practice"
    response_deadline: str | None = None
    player_ids: list[int] = []


class EventUpdateIn(BaseModel):
    title: str
    event_date: str
    location: str
    meal_price: int = 0
    event_type: str = "practice"
    response_deadline: str | None = None
    status: str = "open"
    player_ids: list[int] = []


class PaymentIn(BaseModel):
    player_id: int
    title: str
    amount: int
    due_date: str | None = None
    status: str = "unpaid"
    note: str = ""


# ---------------- Admin APIs ----------------

@app.get("/api/admin/dashboard")
def admin_dashboard(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM players WHERE active=TRUE")
            players = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM parents")
            parents = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM events WHERE event_date >= %s", (date.today(),))
            events = cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE status<>'paid'")
            unpaid = cur.fetchone()["total"]
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM event_players ep
                JOIN events e ON e.id=ep.event_id
                LEFT JOIN attendance a ON a.event_id=ep.event_id AND a.player_id=ep.player_id
                WHERE e.event_date >= %s AND a.id IS NULL
            """, (date.today(),))
            pending_replies = cur.fetchone()["n"]
    return {
        "players": players,
        "parents": parents,
        "events": events,
        "unpaid": unpaid,
        "pending_replies": pending_replies,
    }


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
                       ) AS parents
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
            cur.execute("""
                INSERT INTO players(name,team,number,active)
                VALUES(%s,%s,%s,%s) RETURNING *
            """, (body.name.strip(), body.team.strip(), body.number.strip(), body.active))
            row = cur.fetchone()
        conn.commit()
    return row


@app.put("/api/admin/players/{player_id}")
def update_player(player_id: int, body: PlayerIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE players
                SET name=%s,team=%s,number=%s,active=%s
                WHERE id=%s RETURNING *
            """, (body.name.strip(), body.team.strip(), body.number.strip(), body.active, player_id))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "找不到球員")
    return row


@app.get("/api/admin/parents")
def admin_parents(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pa.*,
                       COALESCE(
                         json_agg(json_build_object('id',p.id,'name',p.name,'team',p.team))
                         FILTER (WHERE p.id IS NOT NULL),
                         '[]'
                       ) AS players
                FROM parents pa
                LEFT JOIN parent_players pp ON pp.parent_id=pa.id
                LEFT JOIN players p ON p.id=pp.player_id
                GROUP BY pa.id
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
                    VALUES(%s,%s,%s,%s) RETURNING *
                """, (
                    body.display_name.strip(), body.line_user_id.strip(),
                    body.phone.strip(), body.is_primary
                ))
                row = cur.fetchone()
            conn.commit()
        return row
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "此 LINE User ID 已存在")


@app.post("/api/admin/bind")
def bind_parent_player(body: BindIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO parent_players(parent_id,player_id)
                VALUES(%s,%s) ON CONFLICT DO NOTHING
            """, (body.parent_id, body.player_id))
        conn.commit()
    return {"ok": True}


@app.delete("/api/admin/bind")
def unbind_parent_player(
    parent_id: int = Query(...),
    player_id: int = Query(...),
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM parent_players WHERE parent_id=%s AND player_id=%s",
                (parent_id, player_id)
            )
        conn.commit()
    return {"ok": True}


@app.get("/api/admin/events")
def admin_events(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.id,e.title,e.event_date::text,e.location,e.meal_price,e.status,e.event_type,
                       e.response_deadline::text,
                       COUNT(ep.player_id) AS invited,
                       COUNT(a.id) AS replied,
                       COALESCE(SUM(CASE WHEN a.attendance_status='attend' THEN 1 ELSE 0 END),0) AS attend,
                       COALESCE(SUM(CASE WHEN a.attendance_status='leave' THEN 1 ELSE 0 END),0) AS leave,
                       COALESCE(SUM(CASE WHEN a.attendance_status='maybe' THEN 1 ELSE 0 END),0) AS maybe,
                       COALESCE(SUM(COALESCE(a.player_meals,0)+COALESCE(a.parent_meals,0)),0) AS meals
                FROM events e
                LEFT JOIN event_players ep ON ep.event_id=e.id
                LEFT JOIN attendance a ON a.event_id=e.id AND a.player_id=ep.player_id
                GROUP BY e.id
                ORDER BY e.event_date DESC,e.id DESC
            """)
            return cur.fetchall()


@app.post("/api/admin/events")
def create_event(body: EventIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO events(title,event_date,location,meal_price,event_type,response_deadline)
                VALUES(%s,%s,%s,%s,%s,%s) RETURNING *
            """, (
                body.title.strip(), body.event_date, body.location.strip(),
                body.meal_price, body.event_type, body.response_deadline or None
            ))
            event = cur.fetchone()
            if body.player_ids:
                cur.executemany(
                    "INSERT INTO event_players(event_id,player_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                    [(event["id"], pid) for pid in body.player_ids]
                )
        conn.commit()
    return event


@app.put("/api/admin/events/{event_id}")
def update_event(event_id: int, body: EventUpdateIn, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE events SET
                  title=%s,event_date=%s,location=%s,meal_price=%s,event_type=%s,
                  response_deadline=%s,status=%s
                WHERE id=%s RETURNING *
            """, (
                body.title.strip(), body.event_date, body.location.strip(), body.meal_price,
                body.event_type, body.response_deadline or None, body.status, event_id
            ))
            event = cur.fetchone()
            if not event:
                raise HTTPException(404, "找不到活動")

            cur.execute("DELETE FROM event_players WHERE event_id=%s", (event_id,))
            if body.player_ids:
                cur.executemany(
                    "INSERT INTO event_players(event_id,player_id) VALUES(%s,%s)",
                    [(event_id, pid) for pid in body.player_ids]
                )
        conn.commit()
    return event


@app.get("/api/admin/events/{event_id}")
def admin_event_detail(event_id: int, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id,title,event_date::text,location,meal_price,status,event_type,response_deadline::text
                FROM events WHERE id=%s
            """, (event_id,))
            event = cur.fetchone()
            if not event:
                raise HTTPException(404, "找不到活動")

            cur.execute("""
                SELECT p.id,p.name,p.team,p.number,
                       a.attendance_status,a.leave_reason,
                       COALESCE(a.player_meals,0) AS player_meals,
                       COALESCE(a.parent_meals,0) AS parent_meals
                FROM event_players ep
                JOIN players p ON p.id=ep.player_id
                LEFT JOIN attendance a ON a.event_id=ep.event_id AND a.player_id=ep.player_id
                WHERE ep.event_id=%s
                ORDER BY p.team,p.name
            """, (event_id,))
            players = cur.fetchall()

    return {"event": event, "players": players}


@app.get("/api/admin/payments")
def admin_payments(authorization: str | None = Header(default=None)):
    require_admin(authorization)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pay.id,pay.player_id,p.name AS player_name,p.team,pay.title,pay.amount,
                       pay.due_date::text,pay.status,pay.note
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
                INSERT INTO payments(player_id,title,amount,due_date,status,note)
                VALUES(%s,%s,%s,%s,%s,%s) RETURNING *
            """, (
                body.player_id, body.title.strip(), body.amount,
                body.due_date or None, body.status, body.note.strip()
            ))
            row = cur.fetchone()
        conn.commit()
    return row


@app.put("/api/admin/payments/{payment_id}/status")
def update_payment_status(
    payment_id: int,
    status: str = Query(...),
    authorization: str | None = Header(default=None)
):
    require_admin(authorization)
    if status not in ("unpaid", "paid", "pending"):
        raise HTTPException(400, "status 錯誤")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE payments SET status=%s WHERE id=%s RETURNING *",
                (status, payment_id)
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "找不到繳費項目")
    return row
