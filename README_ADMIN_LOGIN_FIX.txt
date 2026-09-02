管理後台登入修正

原因：
static/admin.js 內有一段舊的義工管理程式被以 literal \n 字串插入，
造成 JavaScript SyntaxError，導致整個 admin.js 無法執行，
所以 /admin 登入按鈕沒有正常工作。

修正：
- 移除已不用的本地義工 admin JS 區塊
- 保留目前 Google Apps Script 義工入口
- 已用 node --check 驗證 admin.js 語法正常
- app.py 也完成 Python syntax check

更新：
git add .
git commit -m "Fix admin login JavaScript syntax"
git push

Render 部署後請 Ctrl + F5。
