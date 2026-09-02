公告頁前端渲染修正

症狀：
- GET /api/announcements = 200
- 公告頁只看到「這裡會保留球隊過去發送的重要通知」
- 沒有公告卡片，也沒有「目前沒有公告」

修正：
- target_values 支援 array / JSON string / plain string / null
- API 回傳格式增加防呆
- 單筆異常資料不再讓整個公告頁中斷
- 無資料一定顯示「目前沒有公告」
- 發生前端錯誤會直接顯示「公告載入失敗」與原因
- Service Worker cache version 升級，避免舊 app.js 快取

部署後建議：
1. 關閉已安裝的 PWA
2. 手機瀏覽器重新整理一次
3. 再重新開啟 App
