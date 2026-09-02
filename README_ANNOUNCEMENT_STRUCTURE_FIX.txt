公告頁真正根因修正

根因：
confirmExtraBinding() 在舊版中沒有在第二位球員綁定流程後正確結束。
結果 volunteerWeekday() / loadVolunteers() / loadAnnouncements()
都被包在 confirmExtraBinding() 裡，正常登入時根本沒有全域 loadAnnouncements()。

因此點「📢 公告」只會看到 index.html 原本的固定說明。

這版修正：
- 正確關閉 confirmExtraBinding()
- 義工與公告函式恢復為全域
- 移除原本錯置在 loadAnnouncements() 後面的 catch/brace
- 公告頁增加錯誤顯示
- 不修改 PWA、Service Worker、LINE Login 或公告 SQL
