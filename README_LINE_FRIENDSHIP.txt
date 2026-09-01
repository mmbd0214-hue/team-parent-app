LINE 官方帳號好友檢查功能

流程：
1. 家長開啟 LIFF App
2. LINE Login
3. App 呼叫 liff.getFriendship()
4. 已加入「青山社區棒球隊小幫手」→ 正常使用
5. 尚未加入 → 顯示加入好友按鈕
6. 按下後呼叫 liff.requestFriendship()
7. 加入成功後直接進 App

重要：
- LINE Login Channel 必須連結到「青山社區棒球隊小幫手」官方帳號。
- 建議 LIFF 使用 Full size。
- 已綁定球員的家長不需要重新綁定。
