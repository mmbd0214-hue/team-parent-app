家長活動備註功能

- 活動回覆新增「備註（選填）」欄位，出席或請假都可填寫。
- 沿用既有 attendance.attendance_note 欄位，不需新增 Supabase schema。
- 家長查看活動出席名單時，若該球員有填寫備註，會顯示在球員姓名下方。
- 備註內容會做 HTML escape 後顯示。
