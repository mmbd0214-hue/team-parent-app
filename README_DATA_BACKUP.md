# 管理員資料備份

管理後台「總覽」新增「下載完整備份」。

- API：`GET /api/admin/backup`
- 權限：需管理員 Authorization
- 格式：ZIP，內含 UTF-8 BOM CSV 與 `backup_manifest.json`
- 範圍：家長、球員、綁定、活動、賽程、活動對象、出席、繳費、公告、義工、通知/訊息紀錄、已讀狀態
- CSV 可直接用 Excel 開啟。

注意：備份包含個人資料，請勿放到公開 GitHub 或公開雲端連結。
