# Garmin Multi-Account MCP

這是新的正式專案，目標是讓 `ChatGPT Web` 透過公開 HTTPS 連到一個遠端 MCP server，並查詢多個預先配置的 Garmin 帳號。

這個專案的設計來源：

- `../garmin_mcp1`: 參考 Garmin Connect 工具與認證流程
- `../garmin_mcp2`: 參考遠端 HTTP 暴露與 `docker-compose` 思路

但正式程式碼只放在目前這個 `project/` 目錄。

## 目前已完成

- 多帳號 YAML 設定檔
- 每個 Garmin 帳號獨立 token 路徑
- 遠端 MCP 啟動模式
- 第一批常用查詢工具
- Dockerfile
- docker-compose

## 目前提供的工具

- `list_accounts`
- `get_account_status`
- `get_full_name`
- `get_user_profile`
- `get_stats`
- `get_steps_data`
- `get_training_readiness`
- `get_activities_by_date`
- `get_activities_fordate`
- `get_activity`
- `get_activity_splits`

每個查詢工具都需要傳入 `account_id`，避免查到錯的人。

## 專案結構

```text
project/
├── config/
│   └── accounts.example.yaml
├── data/
│   └── tokens/
├── src/
│   └── garmin_multi_mcp/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## 1. 建立帳號設定檔

先複製範例：

```bash
cp config/accounts.example.yaml config/accounts.yaml
```

然後依你的帳號調整 `account_id`、`label`、`token_path` 和 secret 路徑。

範例：

```yaml
token_root: /data/tokens
default_account_id: alice

accounts:
  - account_id: alice
    label: Alice Garmin
    token_path: /data/tokens/alice
    token_base64_path: /data/tokens/alice.b64
    email_file: /run/secrets/garmin_alice_email
    password_file: /run/secrets/garmin_alice_password

  - account_id: bob
    label: Bob Garmin
    token_path: /data/tokens/bob
    token_base64_path: /data/tokens/bob.b64
    email_file: /run/secrets/garmin_bob_email
    password_file: /run/secrets/garmin_bob_password
```

## 2. 先做每個帳號的 Garmin 登入

你需要逐一為每個帳號建立 token。

本機執行方式：

```bash
pip install -e .
garmin-multi-mcp-auth --accounts-file config/accounts.yaml --account-id alice
garmin-multi-mcp-auth --accounts-file config/accounts.yaml --account-id bob
```

驗證 token：

```bash
garmin-multi-mcp-auth --accounts-file config/accounts.yaml --account-id alice --verify
garmin-multi-mcp-auth --accounts-file config/accounts.yaml --account-id bob --verify
```

如果帳號有 MFA，CLI 會在終端機要求你輸入驗證碼。

## 3. 啟動遠端 MCP server

本機直接啟動：

```bash
export GARMIN_ACCOUNTS_FILE=config/accounts.yaml
export MCP_TRANSPORT=http
export MCP_HOST=0.0.0.0
export PORT=38080
export MCP_ALLOWED_HOSTS="192.168.1.100:*,mcp.example.com,mcp.example.com:*"
export MCP_ALLOWED_ORIGINS="http://192.168.1.100:*,https://mcp.example.com,https://mcp.example.com:*,https://chatgpt.com,https://chat.openai.com"
garmin-multi-mcp
```

預設會提供遠端 MCP 入口：

```text
http://localhost:38080/mcp
```

## 4. 使用 Docker Compose

先準備：

```bash
cp config/accounts.example.yaml config/accounts.yaml
mkdir -p data/tokens
```

啟動：

```bash
docker compose up --build -d
```

Compose 預設會把服務暴露在：

```text
http://localhost:38080/mcp
```

如果你要讓 LAN IP 或公開網域可直接連線，需要把它們加入允許清單：

```text
MCP_ALLOWED_HOSTS
MCP_ALLOWED_ORIGINS
```

目前 `docker-compose.yml` 已預設包含：

- `192.168.1.100`（範例 LAN IP，請依實際環境修改）
- `mcp.example.com`（範例網域，請替換為你的網域）

## 5. 連到 ChatGPT Web

你已經可以自行提供 HTTPS，所以只要把 tunnel 對到本機的 `38080` 埠即可。

ChatGPT Web Apps/Connectors 內填入：

```text
https://your-domain.example.com/mcp
```

## 注意事項

- 這個版本目前先實作「多帳號遠端讀取骨架 + 常用工具」。
- `garmin_mcp1` 原本有大量工具，後續可以依相同模式繼續搬進來。
- 目前不做每位使用者自己的 OAuth，而是由伺服器管理員預先配置多組 Garmin 帳號。
