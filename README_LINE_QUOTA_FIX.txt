LINE 額度查詢 500 修正

原錯誤：
NameError: name 'requests' is not defined

原因：
額度查詢 API 使用 requests.get()，但專案未匯入/安裝 requests。

修正：
改用專案原本已使用的 httpx：
- httpx.get(...)
- except httpx.RequestError

不需要修改 requirements.txt，也不需要新增 Render 套件。
