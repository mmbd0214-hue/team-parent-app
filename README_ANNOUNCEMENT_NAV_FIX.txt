公告頁只顯示固定說明文字的修正

檢查結果：
- announcementsPage 存在
- announcementList 存在
- loadAnnouncements() 存在
- 問題在於家長端 nav click handler 沒有可靠呼叫 loadAnnouncements()

修正：
- 點「📢 公告」時明確執行 await loadAnnouncements()
- 載入時先顯示「公告載入中...」
- 若 API 回空陣列會顯示「目前沒有公告」
- 若 API 發生錯誤會顯示錯誤訊息
- 不修改 PWA / Service Worker / LINE Login / 後台公告編輯功能
