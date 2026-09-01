# 球隊家長 App 完整版

整合功能：
- LINE Login / LIFF
- 首次登入自動取得 LINE User ID
- Supabase parents 自動建立
- 家長自助輸入球員綁定碼
- 球員綁定碼預覽與確認
- 一位家長可綁多位球員
- 一位球員可限制最多家長數
- 家長端：活動、出席、請假、訂餐、繳費
- `/admin` 管理後台
- 球員新增 / 編輯 / 停用
- 綁定碼查看 / 複製 / 重設
- 家長與球員綁定 / 解除
- 建立練球 / 比賽 / 活動
- 每場指定球員
- 回覆截止日期
- 出席 / 請假 / 未回覆 / 餐點統計
- LINE 通知對象預覽
- 發送全部通知
- 只提醒未回覆
- 通知紀錄
- 繳費新增與狀態管理
- `/health` Render health check

## Render Environment

必要：
- DATABASE_URL
- ADMIN_PASSWORD
- LINE_CHANNEL_ACCESS_TOKEN
- LINE_LIFF_ID
- APP_BASE_URL
- MOCK_LOGIN=0

## LINE Login / LIFF

Endpoint URL:
https://你的-render-網址.onrender.com/

## 更新現有專案

建議先備份目前版本，再將這個完整版的所有檔案覆蓋到 repo 根目錄。

然後：

```powershell
git add .
git commit -m "Integrate full team app"
git push
```

Render Auto Deploy 會自動更新。


## 多場比賽
- 集合時間可設定或標示未定
- 同一活動可新增多個比賽場次
- 每場可設定比賽時間、時間未定與對戰對手
- 家長端與 LINE 通知同步顯示
