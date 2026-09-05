出席調查功能更新

1. 練球：
   - 回覆選項改為「出席 / 請假 / 上午請假 / 下午請假」
   - 「上午請假」存為 attendance_status=attend + practice_duration=morning_leave
   - 「下午請假」存為 attendance_status=attend + practice_duration=afternoon_leave
   - 舊資料 practice_duration=half 仍可讀取，顯示為「半天（舊資料）」

2. 比賽：
   - 維持「出席 / 請假」
   - 選「出席」後顯示「出席備註」
   - 可填晚點到、第二場無法打等

3. 請假原因：
   - 「請假 / 上午請假 / 下午請假」皆可填寫請假原因

4. 後台活動統計：
   - 練球顯示「出席 / 上午請假 / 下午請假」
   - 舊半天資料顯示「半天（舊資料）」
   - 比賽顯示家長出席備註

不需要新增資料庫欄位，沿用：
- attendance.practice_duration
- attendance.attendance_note
