繳費管理刪除功能

新增：
- DELETE /api/admin/payments/{payment_id}
- /admin 繳費管理加入「刪除」按鈕
- 刪除前會顯示球員、項目、金額與狀態
- 刪除只影響 payments 該筆資料
- 不會刪除球員、家長、活動或出席資料

更新後：
git add .
git commit -m "Add payment delete support"
git push
