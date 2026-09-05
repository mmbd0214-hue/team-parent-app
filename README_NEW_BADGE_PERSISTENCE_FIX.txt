NEW 提示永久顯示修正

原因：舊版以瀏覽器 localStorage 記錄已讀狀態，在 LINE LIFF / PWA 環境可能因儲存空間或 WebView 狀態造成已讀基準不穩定，導致重新登入後又判定為 NEW。

修正：
1. 新增 parent_content_seen 資料表，由 Supabase/PostgreSQL 永久保存每位家長的已讀狀態。
2. 首頁活動、公告、繳費的 NEW 都改用後端已讀基準判斷。
3. 點進對應頁面後立即寫回已讀狀態，重新登入/換裝置後仍能保留。
4. 繳費依不同球員分開記錄已讀狀態。
5. 第一次升級此版本時，以目前資料建立基準，不把所有既有資料誤判為 NEW。
6. Service Worker cache 升級至 v9。

不需手動修改 Supabase schema；程式啟動時會自動 CREATE TABLE IF NOT EXISTS。
