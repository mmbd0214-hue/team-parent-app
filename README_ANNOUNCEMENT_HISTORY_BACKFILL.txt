歷史 LINE 訊息自動匯入 App 公告

這版部署後，init_db() 會自動把既有 message_logs 匯入 announcements。

規則：
- 同一次群發只建立一則公告
- 新版有 batch_id：依 batch_id 合併
- 舊版沒有 batch_id：依同一天 + 對象 + 相同訊息內容合併
- 全部家長公告：後來加入的家長也可看到
- 組別公告：會從 target_label 還原 U10/U12/U13/U15
- 指定家長公告：會由當時 message_logs 的 parent_id 還原
- 後台對單一家長直接回覆（target_label=單一家長）不匯入公告
- 已經同步過的公告會跳過，避免重複

不需要手動操作 Supabase。
