公告歷史訊息即時合併修正版

這版不再依賴 startup backfill。

家長打開 /api/announcements 時，後端會直接合併：
1. announcements
2. message_logs 裡歷史全部家長訊息
3. message_logs 裡歷史組別訊息
4. message_logs 裡此家長曾收到的指定家長訊息

同一則公告會去重，不會重複顯示。

另外新增：
GET /api/admin/announcements/diagnostics

可查看：
- announcements 筆數
- message_logs 筆數
- message_logs 各 target_type 筆數
