# AI 用量 Dashboard

iPhone 睇得到嘅 Grok／Muse 共用池用量頁。資料來自 box 上嘅 script（主）同 AI 自報（後備），只存 % 同時間。

**正式頁（GitHub Pages）**：https://dheimanb.github.io/ai-usage/  
（repo：https://github.com/dheimanb/ai-usage ）

依據：PRD v4（Notion「AI 使用量 Dashboard」）＋ agent-handoff issue #17。

## 檔案

| 檔 | 做咩 |
|---|---|
| `index.html` ＋ `view.js` | iPhone 頁面（冇 CDN；相對路徑讀 `usage.json`） |
| `usage.json` | 快照（公開）。每行：service、used_pct、reset_at、updated_at、source |
| `usage.schema.json` ＋ `validate_usage.py` | Schema 同驗證 |
| `grok_usage.py` | 讀 Grok 共用週額度，寫 `usage.json` 嘅 grok 行 |
| `cdp_pipe.py` ＋ `usage_lib.py` | Chrome pipe 控制、原子寫入／合併 |
| `login.sh` | heiman 喺 **box 桌面** 開專用 profile 登入（本地） |
| `push_usage.sh` | 只 commit＋push `usage.json`（有改先推） |
| `preview.png` ／ `preview-states.png` | 預覽圖（可選） |
| `test_usage.py`、`test_view.js` | 測試 |

## 重要：profile 只留喺 box

- `profile-grok/` 有登入狀態，**永遠唔 commit、唔上傳、唔放上 Pages**。
- `.gitignore` 已忽略 `profile-grok/`、`__pycache__/`、`.chrome*` 等。
- Script 只讀畫面 `innerText` 入記憶體，唔寫 cookie／token 入任何檔。

## 點開 Pages

1. 用 iPhone Safari 開：https://dheimanb.github.io/ai-usage/
2. 「加到主畫面」可以當 App 用。
3. 頁面每 5 分鐘自動重新讀 `usage.json`；亦可以撳「重新整理」。

門檻色：≥70% 黃「慳住用」；≥90% 紅「只做急嘢」；≥97%（剩 ≤3%）「停，報 heiman」。`updated_at` 舊過 24 個鐘標「舊數」。

## usage.json

```json
{
  "schema_version": 1,
  "rows": [
    {"service": "grok", "name": "Grok 共用池", "used_pct": 58.0,
     "reset_at": "2026-10-30T16:19:00+08:00", "updated_at": "2026-10-29T02:55:03+08:00", "source": "script"},
    {"service": "muse", "name": "Muse", "used_pct": null, "reset_at": null, "updated_at": null, "source": "ai-self"}
  ]
}
```

- 只放 % 同時間；驗證器拒絕多餘欄位（例如 token／cookie）。
- Grok 一行共用池；`muse` 由 bibi 喺佢部機寫。

## 喺 box 真讀 Grok

```bash
cd /home/box/ai-usage

# heiman 喺 box 桌面登入一次（之後閂視窗）
DISPLAY=:8 ./login.sh

python3 grok_usage.py --dry-run    # 只印
python3 grok_usage.py              # 寫 usage.json
python3 validate_usage.py
python3 test_usage.py && node test_view.js
```

用量頁：`https://grok.com/?_s=usage`。退出碼：0 成功；2 冇 profile；3 似未登入；4 搵唔到 %；5 瀏覽器錯。2–5 唔寫檔。

本地預覽頁：`python3 -m http.server 8765 --bind 127.0.0.1` → http://127.0.0.1:8765/

## 手動再 push usage.json

```bash
cd /home/box/ai-usage
python3 grok_usage.py          # 可選：先更新數
./push_usage.sh                # 有改先 commit＋push usage.json
```

首次要有 remote（repo 建好之後）：

```bash
cd /home/box/ai-usage
git remote add origin https://github.com/dheimanb/ai-usage.git   # 若未加
git push -u origin main
```

每小時 routine（由 parent／大佬開，唔裝 systemd／cron）應行：

```bash
cd /home/box/ai-usage && python3 grok_usage.py && ./push_usage.sh
```

## 安全

- AI 唔登入、唔讀／抄 cookie 或 token。
- `cdp_pipe.py` 白名單只有開頁、讀 text、截圖等少數指令。
- 公開 repo 只應有：頁面、schema、script 源碼、`usage.json`（%＋時間）、README、預覽圖。
