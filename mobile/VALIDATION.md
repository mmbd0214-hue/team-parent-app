# 本機驗證紀錄

日期：2026-10-02。Web 基準：`39173d56af8e642301b1f53adad31a184a19bf1f`。

本紀錄適用本專案根目錄的後端及 `mobile/`，交付包為 `artifacts/team-parent-mobile-source.zip`。

| 檢查 | 結果 |
| --- | --- |
| Flutter 3.47.6／Dart 3.13.5 靜態分析 | `flutter analyze` 無問題 |
| Flutter 測試 | 5 項通過：並行刷新、刷新途中登出、球員切換競態、付款前導零與未回覆、綁定預覽確認 |
| Python 3.12.15／PostgreSQL 17.6 整合測試 | 26 項通過；只使用獨立本機測試資料庫 |
| Web JavaScript | Node 24.21.0 檢查 `static/app.js` 與 `static/admin.js` 通過 |
| Git 差異空白檢查 | `git diff --check` 通過 |

後端測試涵蓋舊憑證拒絕、session 撤銷、刷新重放（含並行）、跨球員權限、共同家長版本衝突、關閉與截止活動、付款狀態競態、後五碼／日期、管理員撤權、一次性 handoff／CSRF、公告過濾及分頁、已讀遞增、Excel 前導零及公式文字、帳號刪除保留共用資料、migration 冪等與管理欄位錯誤。Apple 測試使用本機 RSA 簽章與模擬 provider，驗證 nonce、加密 token 保存及撤銷佇列；沒有連線至 Apple 正式服務。

Python 測試出現 3 項框架棄用警告（FastAPI startup event 與 Starlette／AnyIO），沒有測試失敗。

## 尚待發行環境驗證

本機沒有 Android SDK；Windows 不能建置 iOS。未產生 APK／AAB／IPA，未跑 GitHub Actions，未驗證 LINE／Apple 真機 callback、實際網域關聯、商店簽章、正式 DB 升級或 Supabase／Render 部署。

請依 `WEB_TO_FLUTTER_APP_SPEC.md` A01–A25 完成 staging 與真機驗收。本機測試不能代替所有驗收條件。P2 推播、原生義工與完整原生管理端未包含於此 V1。

## 部署及回復順序

1. 備份正式資料庫；先在 staging 副本套用 `migrations/001_mobile.sql`，核對家長綁定、活動參加名單、歷史訂餐及付款筆數。
2. 配置 HTTPS、LINE／Apple 登入、隱私與客服網址、Apple 撤銷 worker、簽章與深連結關聯。管理密碼至少 12 字元，禁止使用範例值。
3. 同批更新後端與 Web，要求舊登入重新驗證；完成跨家長／跨球員、付款衝突、帳號刪除與 Web 後台驗收，再發行 App。
4. 發行故障先暫停 App 使用（`APP_MAINTENANCE=1`），回復至已驗證且使用安全 session 的版本。不要回復接受可猜測字串 token 的舊後端。
5. 此 migration 增量新增欄位／表，不提供自動 destructive down migration。必要時由負責人於維護窗口還原已演練的 DB 備份，先核對發行後新增資料，再解除維護。
