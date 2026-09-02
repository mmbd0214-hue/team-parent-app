公告頁快取修正

症狀：
- GET /api/announcements = 200
- 公告頁只顯示固定說明文字
- 新版 loader 的「載入中 / 沒有公告 / 錯誤」都沒有出現

判斷：
手機/PWA 很可能仍在執行舊 static/app.js。

修正：
1. app.js URL 加版本號：
   /static/app.js?v=20260902-announcements-v5
2. style.css URL 加版本號
3. Service Worker cache key 升版
4. Service Worker 不再預快取首頁 /
5. 登入完成後就直接 GET /api/announcements
6. 點公告頁時先 render 已載入資料，再重新抓最新

部署後請：
- 完全關閉已安裝 PWA 再重開
- 若仍舊，刪除桌面 App 後重新加入主畫面一次
