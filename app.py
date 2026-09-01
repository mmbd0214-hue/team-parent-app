
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
MOCK_LOGIN = os.getenv("MOCK_LOGIN", "0") == "1"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-now")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_LIFF_ID = os.getenv("LINE_LIFF_ID", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")

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

            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT ''")
            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT TRUE")
            cur.execute("ALTER TABLE parents ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")

            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS number TEXT DEFAULT ''")
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE")
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS bind_code TEXT")
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS max_parents INTEGER NOT NULL DEFAULT 2")

            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'practice'")
            cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS response_deadline DATE")
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {"liff_id": LINE_LIFF_ID, "mock_login": MOCK_LOGIN}


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
                SELECT 1 FROM events
                WHERE id=%s AND status='open'
                  AND (response_deadline IS NULL OR response_deadline >= %s)
            """, (event_id, date.today()))

            if not cur.fetchone():
                raise HTTPException(403, "活動已截止")

            cur.execute("""
                INSERT INTO attendance(
                    event_id,player_id,attendance_status,
                    leave_reason,player_meals,parent_meals
                )
                VALUES(%s,%s,%s,%s,%s,%s)
                ON CONFLICT(event_id,player_id) DO UPDATE SET
                    attendance_status=EXCLUDED.attendance_status,
                    leave_reason=EXCLUDED.leave_reason,
                    player_meals=EXCLUDED.player_meals,
                    parent_meals=EXCLUDED.parent_meals
            """, (
                event_id,body.player_id,body.attendance_status,
                body.leave_reason.strip(),body.player_meals,body.parent_meals
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


# ---------------- Admin auth ----------------

class AdminLogin(BaseModel):
    password: str


@app.post("/api/admin/login")
def admin_login(body: AdminLogin):
    if not secrets.compare_digest(body.password, ADMIN_PASSWORD):
        raise HTTPException(401, "管理員密碼錯誤")
    return {"token": f"admin:{ADMIN_PASSWORD}"}


def require_admin(authorization):
    expected = f"Bearer admin:{ADMIN_PASSWORD}"
    if not authorization or not secrets.compare_digest(authorization, expected):
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


class NotifyIn(BaseModel):
    mode: str = "all"
    primary_only: bool = False


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
                SELECT pa.id,pa.line_user_id,pa.display_name,pa.picture_url,pa.phone,pa.is_primary,pa.last_login_at,
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
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
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
