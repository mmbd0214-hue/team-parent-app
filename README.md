# 球隊家長 App - Supabase PostgreSQL 版

這一版已從 SQLite 改成 PostgreSQL，適合部署到 Render，資料庫使用 Supabase。

## 1. 建立 Supabase 專案

進入 Supabase Dashboard 建立新專案。

建立完成後到：

Project Settings → Database

找到 PostgreSQL Connection String。

建議使用 Transaction pooler 或 Session pooler 的連線字串，並確保 SSL 可用。

你需要一條類似：

```text
postgresql://postgres.xxxxx:PASSWORD@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres?sslmode=require
```

請把真正密碼放進連線字串。

## 2. 本機測試

PowerShell：

```powershell
$env:DATABASE_URL="你的 Supabase PostgreSQL connection string"
$env:MOCK_LOGIN="1"

python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

第一次啟動時程式會自動建立：

- parents
- players
- parent_players
- events
- attendance
- payments

如果 MOCK_LOGIN=1 且資料庫是空的，也會建立 Demo 資料。

## 3. Render 部署

GitHub push 後，在 Render 使用 Blueprint 或 Web Service。

Render Environment Variables：

```text
DATABASE_URL = Supabase PostgreSQL connection string
MOCK_LOGIN = 1
```

測試完成、正式串 LINE 前，再把：

```text
MOCK_LOGIN=0
```

## 4. 注意

請不要把真實 DATABASE_URL、資料庫密碼 commit 到 GitHub。
`.env` 已加入 `.gitignore`。

正式版之後建議再加：
- 簽章 Session / JWT
- 管理員後台
- 比賽指定球員與通知名單
- LINE Messaging API
