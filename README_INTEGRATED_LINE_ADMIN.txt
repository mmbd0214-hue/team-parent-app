家長 App + LINE 管理員權限整合

功能：
1. parents 自動新增 is_admin 欄位，預設 FALSE。
2. 原 /admin 密碼登入仍保留，可作為第一位管理員授權入口。
3. /admin → 家長管理：
   - 每位家長多一個「一般家長 / 管理員」按鈕。
   - 可授予或取消管理員權限。
4. 被授權的 LINE 家長登入家長 App 後：
   - 底部自動多出「⚙️ 管理」。
   - 一般家長完全不顯示此按鈕。
5. 點「⚙️ 管理」：
   - 後端再次驗證此 parent.is_admin。
   - 成功後取得 parent-admin session。
   - 在家長 App 內嵌完整管理後台。
6. Admin API 後端也會驗證 is_admin。
   - 不是只把按鈕藏起來。
   - 一般家長即使手動呼叫 API 也無法操作。
7. 原本 ADMIN_PASSWORD 登入方式保留，避免沒有任何 LINE 管理員時無法進後台。

第一次設定：
A. 先用原本 /admin 密碼登入。
B. 家長管理 → 找到自己的 LINE 家長帳號。
C. 點「一般家長」改成「✅ 管理員」。
D. 關閉並重新開啟家長 App。
E. 底部就會出現「⚙️ 管理」。

注意：
管理員權限綁定的是 parents.line_user_id 所代表的 LINE 登入帳號。
