NEW 圖示永久顯示修正

原因：.navNewBadge 使用 display:block!important，且規則位於 .hidden 之後，因此即使 JavaScript 加上 hidden class，CSS 仍強制顯示 NEW。

修正：新增 .navNewBadge.hidden { display:none!important; }，讓首頁、公告、繳費的 NEW 可以依已讀狀態正確隱藏。
