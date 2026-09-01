# LINE 比賽通知修補包

新增功能：
- 比賽/活動通知對象預覽
- 指定活動球員即為通知對象
- 自動找到球員綁定家長
- 可選「只通知主要家長」
- 未回覆名單統計
- 「發送比賽通知」
- 「只提醒未回覆」
- LINE 發送結果與歷史紀錄
- notification_logs 資料表自動建立

## 覆蓋方式

將：
- app.py
- static/admin.html
- static/admin.css
- static/admin.js

覆蓋到目前專案。

## Render Environment 新增

```text
LINE_CHANNEL_ACCESS_TOKEN=<LINE Messaging API Channel Access Token>
APP_BASE_URL=https://你的-render-網址.onrender.com
```

既有：
```text
DATABASE_URL=...
MOCK_LOGIN=1
ADMIN_PASSWORD=...
```

## LINE 尚未設定時

後台仍能正常：
- 看通知對象
- 看未回覆名單

但按發送後會記錄為 failed，錯誤會顯示：
`LINE_CHANNEL_ACCESS_TOKEN 尚未設定`

## Git 更新

```powershell
git add .
git commit -m "Add LINE event notifications"
git push
```
