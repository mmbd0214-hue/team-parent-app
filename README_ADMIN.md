# /admin 後台修補包

此修補包適用於目前已部署在 Render + Supabase PostgreSQL 的球隊 App。

## 包含檔案

- `app.py`：新增管理 API、event_players、資料表安全 migration
- `static/admin.html`
- `static/admin.css`
- `static/admin.js`

不會覆蓋你現有的：
- `static/index.html`
- `static/app.js`
- `static/style.css`

## 安裝方式

把這個修補包的檔案複製到現有專案根目錄。

結果應為：

```text
team_parent_app_supabase/
├─ app.py
├─ requirements.txt
├─ render.yaml
└─ static/
   ├─ index.html
   ├─ app.js
   ├─ style.css
   ├─ admin.html
   ├─ admin.css
   └─ admin.js
```

## Render 環境變數

除了原本：

```text
DATABASE_URL=...
MOCK_LOGIN=1
```

請新增：

```text
ADMIN_PASSWORD=請設定一個強密碼
```

不要把 ADMIN_PASSWORD 寫進 GitHub。

## 更新 GitHub

```powershell
git add .
git commit -m "Add admin dashboard"
git push
```

Render Auto Deploy 開啟時會自動部署。

部署成功後：

```text
https://你的-render-網址.onrender.com/admin
```

## 管理後台目前功能

- Dashboard
- 球員新增/編輯/停用
- 家長新增
- 家長與球員綁定/解除
- 建立活動/練球/比賽
- 每場活動指定球員
- 回覆截止日期
- 活動統計
- 出席/請假/未回覆
- 球員餐/家長餐統計
- 新增繳費項目
- 已繳/未繳/待確認狀態

正式上線前，管理員登入後續建議再升級成：
- HttpOnly signed session
- 多管理員帳號
- MFA 或 Google/LINE 管理員登入
