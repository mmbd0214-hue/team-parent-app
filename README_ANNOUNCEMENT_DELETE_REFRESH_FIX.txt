公告刪除與重新整理修正

1. App 公告改以 announcements 表為唯一資料來源。
2. 不再即時合併 message_logs，避免已刪公告重新出現。
3. 停止啟動時將歷史 message_logs 自動回填為公告。
4. 家長端公告頁新增「重新整理」按鈕。
5. GET API 使用 no-store，避免瀏覽器沿用舊回應。
6. 公告 API id 改回數字，讓 NEW 已讀判斷正常運作。
