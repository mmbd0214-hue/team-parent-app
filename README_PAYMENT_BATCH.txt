繳費管理批次建立功能

新增收費時可選：
- 全部球員
- U10
- U12
- U13
- U15
- 單一球員

後端：
POST /api/admin/payments/batch

建立方式：
- 選全部：所有 active=true 球員各建立一筆 payment
- 選組別：該 team 的 active=true 球員各建立一筆
- 選單一：只建立該球員
- 之後每筆仍可獨立改為已繳 / 待確認 / 未繳 / 刪除

更新：
git add .
git commit -m "Add batch payment targets"
git push
