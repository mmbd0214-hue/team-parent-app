# 青山棒球家長 Flutter App

本次交付與實際驗證結果見 [VALIDATION.md](VALIDATION.md)。根目錄執行 `python scripts/export_source.py` 可重建完整原始碼 ZIP（含後端、Web、migration、Flutter、CI 與檔案雜湊清單）；`python scripts/export_openapi.py` 可更新 [OpenAPI 契約](api/openapi.json)。交付包不包含私鑰、本機設定或建置快取。

這是依 `WEB_TO_FLUTTER_APP_SPEC.md` V1 實作的 Android／iOS 原始碼，基準為 Web commit `39173d56af8e642301b1f53adad31a184a19bf1f`。Flutter 為原生家長介面，管理員使用安全交接後的 Web 後台；完整原生後台、推播與原生義工屬規格的 P2。

## 功能

- 原生 LINE 登入、加密 session 儲存、刷新輪替、登出；可設定 Apple 登入。
- 綁定碼預覽／確認、多球員與帳號隔離的球員選擇記憶。
- 個別球員受邀活動、集合與多場比賽、出席／請假／未確定、部分練球、備註及出席名單。
- 公告分頁、安全 HTTPS 連結與跨裝置 NEW；繳費依球員區分已讀。
- 現金／轉帳繳費回報、後五碼、待確認／已繳；版本檢查防止覆寫。
- Google 義工外部入口、管理員 Web 後台、隱私／客服、重新驗證後刪除帳號。
- 深連結、前景刷新、錯誤／空白／載入頁、最低版本與維護設定、繁體中文與既有球隊 icon。

原始碼完成不等於已上架：實際 LINE／Apple、HTTPS 網域與商店簽章需設定，並在真機驗證。沒有連正式 Supabase、部署或執行正式資料 migration。

## 工具版本與平台

本次使用 Flutter **3.47.6**、Dart **3.13.5**、Python **3.12.15**。依賴版本記錄於 `pubspec.lock`。Android minSdk 24；iOS 專案最低 15.0。iOS 建置必須在 macOS／Xcode；本機 Windows 缺 Android SDK，所以不宣稱已產生 APK／IPA。

App 識別碼預設 `tw.qingshan.teamparent`（Android namespace 維持 `tw.qingshan.team_parent`）；建立商店 App 前確認可用性。staging 如需與 production 同時安裝，另設原生 App ID、LINE channel、Apple audience 及 domain association。`APP_ENV` 是 Dart 環境設定，不會自動建立 Xcode schemes／Android product flavors。

## 本機啟動

1. 安裝 Flutter／Android SDK，macOS 另安裝 Xcode；執行 `flutter doctor`。
2. 先依下方完成後端 migration 與 staging 環境。
3. 複製 `config/development.example.json` 為 `config/development.local.json`，填入真實 HTTPS API host 及 **LINE Login channel ID**（不是 LIFF ID）。
4. 在 `mobile/` 執行：

```powershell
flutter pub get --enforce-lockfile
flutter run --dart-define-from-file=config/development.local.json
```

本次下載的工具都在根目錄 `.tooling/`，不進 Git；若沿用它們，從 `mobile/` 呼叫 `..\.tooling\flutter\bin\flutter.bat`。若預設沙箱無法建立 Dart 使用者快取或下載依賴，需在可存取的開發環境執行。

`ALLOW_MOCK_LOGIN=true` 僅允許 `APP_ENV=development`，且後端也需 `MOCK_LOGIN=1`／`APP_ENV=development`。正式 App／後端均禁止 mock。Android manifest 禁止明文 HTTP，開發亦建議 HTTPS staging。

## 後端發行步驟

本次更新後端 `app.py`、`mobile_api.py`、`session_security.py`、`apple_identity.py` 與 Web UI。新的 backend 必須與 migration、Web 更新一起交付。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:DATABASE_URL = 'postgresql://YOUR-STAGING-DATABASE'
.venv\Scripts\python.exe scripts/migrate.py
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

先備份、在 staging 還原既有資料，再執行 `migrations/001_mobile.sql`；也可在 Supabase SQL Editor 明確選擇 staging 後執行此 SQL。新空白資料庫才使用 `scripts/migrate.py --bootstrap`，它拒絕已存在 parents 的資料庫。沒有將 migration 加進 startup 或自動連正式 DB。

新版本啟動只檢查 migration 存在，已移除啟動時的歷史回填副作用。舊 `parent:<id>`、`parent-admin:<id>`、含密碼的 admin token 全拒絕；升級後 Web 使用者需重新登入。管理員改為 HttpOnly／Secure cookie 和 CSRF。

設定根目錄 `.env.example` 中的變數。特別需要 `DATABASE_URL`、安全 `ADMIN_PASSWORD`、`LINE_LOGIN_CHANNEL_ID`、既有 LINE Messaging 配置、`LINE_LIFF_ID`、`APP_BASE_URL`。程式不會自動讀取 `.env`，請在 shell／Render 設環境或使用 uvicorn `--env-file`。`PRIVACY_URL`／`SUPPORT_URL` 必須指向球隊的實際公開 HTTPS 頁。

`APP_BASE_URL` 應與 Web origin、App API host 一致；管理 handoff 固定同一個 HTTPS 網域，禁止 arbitrary redirect。uvicorn 使用 `--no-access-log` 避免把一次性 handoff query 寫入 access logs，亦須在上游 proxy 日誌排除该 query。

### LINE Console

在現有 provider 的 LINE Login channel 設 native app，保留既有 LINE User ID 對應。設定 Android package／簽章及 iOS bundle，確認與 LINE Official Account 的關聯。在 staging 真機測試已裝／未裝 LINE、取消、返回、既有家長綁定及帳號切換。不得把 Messaging access token 或 channel secret 放 Dart 設定。

### Apple（若送審需要等效登入）

啟用 `ENABLE_APPLE_LOGIN=true`，配置 Apple capability、bundle audience 與後端 `APPLE_CLIENT_ID`、`APPLE_TEAM_ID`、`APPLE_KEY_ID`、`APPLE_PRIVATE_KEY`。`IDENTITY_ENCRYPTION_KEY` 為伺服器 Fernet key，使用下列指令在自己的安全環境產生並存進 secret manager；不得提交或分享輸出。

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

流程檢查 Apple JWT、issuer／audience／nonce、一次性 challenge 與 code exchange，將 provider refresh token 加密保存。刪除帳號時移除 identity 並排入 provider 撤銷佇列；發行前必須設定定時工作呼叫 `python scripts/process_provider_revocations.py`，監測 pending 工作並重試。完成工作後清空加密 token，不把 provider token 放日誌。

Apple／LINE 新身分不依姓名或 email 自動合併。Apple 使用者可用球員綁定碼連結共用球員，沒有 LINE User ID 時不接收 LINE 通知。此版沒有自助將 Apple 身分合併至另一個已存在 LINE 家長帳號的 UI；需要時應做雙身分驗證的獨立遷移。

## 深連結

- `qingshan://events/123`、`qingshan:///events/123`。
- `https://YOUR-HOST/?event=123`、`https://YOUR-HOST/events/123`。
- App 未安裝時 `/events/123` 轉到 Web 的活動入口；過去活動可在 App 詳情查看，舊 Web 的近期清單限制仍存在。
- 多球員先選參加球員，未受邀時後端拒絕；不從連結取得權限。

Android intent host 從 `API_BASE_URL` 的 Dart define 取得；後端 `ANDROID_SHA256_CERT_FINGERPRINTS` 填入商店 App Signing SHA-256（可逗號分隔），`/.well-known/assetlinks.json` 提供關聯。debug 簽章與商店簽章不同，應各用對應 staging／production 配置。

iOS 複製 `ios/Flutter/Deployment.example.xcconfig` 為 `Deployment.local.xcconfig` 並填 `APP_LINK_HOST`；專案已引用 Runner entitlements。後端填 `IOS_APP_TEAM_ID`，提供 `/.well-known/apple-app-site-association`；Apple Developer 憑證需啟用 Associated Domains 與 Apple Sign In。未設定關聯時不要宣称 HTTPS 連結已驗證可開 App。

## 建置、簽章與 CI

```powershell
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build apk --debug --dart-define-from-file=config/development.local.json
flutter build appbundle --release --dart-define-from-file=config/production.local.json
```

Android release 必須有 `android/key.properties`（keyAlias、keyPassword、storeFile、storePassword）和真正的 keystore；缺少時明確失敗，不用 debug key 偽裝正式包。key／local config 皆在 gitignore。

macOS 於 Xcode 設 team、bundle、capabilities、簽章，確認 API host／隱私／客服與 production Console 後：

```sh
flutter build ipa --release --dart-define-from-file=config/production.local.json
```

`.github/workflows/mobile.yml` 包含 PostgreSQL backend 測試、Web JS 語法、Flutter 分析／測試、Android debug 與 macOS iOS 無簽章建置。此 workflow 已寫入原始碼，本次沒有 push 或在 GitHub 執行；平台建置結果須以 CI／真機結果為準。

## 測試與資料隔離

Flutter 測試使用記憶體憑證及 mock HTTP；後端使用本機全新 PostgreSQL，並拒絕任何非 `127.0.0.1:55432` 或資料庫名稱非 `_test` 結尾的連線。後端測試會清空該測試庫的資料，絕不可指向有需保存資料的 DB。

```powershell
$env:TEST_DATABASE_URL = 'postgresql://postgres@127.0.0.1:55432/team_mobile_test'
.venv\Scripts\python.exe -m pytest tests -q
```

驗收仍需使用 `WEB_TO_FLUTTER_APP_SPEC.md` 的 A01–A25 真機／staging 清單：外部登入 callback、LINE User ID 一致性、兩位家長、多球員深連結、角色撤銷、外部義工、長名單、大字級及真實商店簽章都不能以 mock 測試取代。

### 知道的交付界線

- 沒有推播、線上付款、App 聊天、原生義工或完整原生管理後台，與規格 V1/P2 分工一致。
- 沒有操作正式資料庫、LINE/Apple Console、商店或部署。沒有商店審查通過的宣稱。
- 餐點不新增 UI，更新出席時保留舊餐數；僅當活動關閉訂餐才歸零。
- 公告已讀仍是最大 ID，不把編輯／付款狀態更新當新公告，也不是逐筆 read receipt。
- 帳號刪除移除家長個資及綁定、匿名化通知並清除個人對話；共用球員的出席與繳費保留。備份內個資的保留期限／銷毀作業仍需球隊在發行前定案並納入隱私政策。
- 新增安全與 API 功能的實際設定、Apple 撤銷 worker 排程及商店準備，是部署工作；請勿直接用 example 占位值發行。
