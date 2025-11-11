# ProWaveDAQ 即時資料可視化系統

## 系統概述

ProWaveDAQ 即時資料可視化系統是一個基於 Python 的振動數據採集與可視化平台，用於從 **ProWaveDAQ**（Modbus RTU）設備取得振動數據，並在瀏覽器中即時顯示所有資料點的連續曲線，同時自動進行 CSV 儲存。

本系統提供完整的 Web 介面，讓使用者可以透過瀏覽器操作，不需進入終端機，即可：
- 修改設定檔（`ProWaveDAQ.ini`、`Master.ini`）
- 輸入資料標籤（Label）
- 按下「開始讀取」即啟動採集與即時顯示
- 系統同時自動分檔儲存資料（根據 `Master.ini` 的秒數）
- 按下「停止」即可安全結束

## 功能特性

### 核心功能
- **即時資料採集**：透過 Modbus RTU 協議從 ProWaveDAQ 設備讀取振動數據
- **即時資料可視化**：使用 Chart.js 在瀏覽器中顯示多通道連續曲線圖
- **自動 CSV 儲存**：根據設定檔自動分檔儲存資料
- **Web 介面控制**：完整的瀏覽器操作介面，無需終端機
- **設定檔管理**：透過 Web 介面直接編輯 INI 設定檔

### 技術特性
- 使用 Flask 提供 Web 服務
- 使用 Chart.js 實現即時圖表（每 200ms 更新）
- 多執行緒架構，確保資料採集與 Web 服務不互相干擾
- 記憶體中資料傳遞，高效能即時處理
- 支援多通道資料顯示（預設 3 通道）

## 系統需求

### 硬體需求
- ProWaveDAQ 設備（透過 Modbus RTU 連接）
- 串列埠（USB 轉串列埠或直接串列埠）
- 支援 Python 3.9+ 的系統（建議 DietPi 或其他 Debian-based 系統）

### 軟體需求
- Python 3.9 或更高版本
- 支援的作業系統：
  - DietPi（建議）
  - Debian-based Linux 發行版
  - Ubuntu
  - Raspberry Pi OS

### Python 套件依賴
請參考 `requirements.txt` 檔案，主要依賴包括：
- `pymodbus>=3.11.3` - Modbus 通訊
- `pyserial>=3.5` - 串列埠通訊
- `Flask>=3.1.2` - Web 伺服器

## 安裝說明

### 1. 克隆或下載專案
```bash
cd /path/to/ProWaveDAQ_Python_Visualization_Unit
```

### 簡易安裝指令
```bash
./deploy.sh
```

**注意**：`deploy.sh` 腳本在以下情況需要 `sudo` 權限：
- 系統未安裝 Python 3、pip3 或 venv 模組時（需要安裝系統套件）
- 需要將用戶加入 `dialout` 群組以存取串列埠時

如果系統已安裝 Python 環境且用戶已在 `dialout` 群組中，則不需要 `sudo`。

若需要 `sudo`，請執行：
```bash
sudo ./deploy.sh
```

### 2. 安裝 Python 依賴套件
```bash
pip install -r requirements.txt
```

或使用 pip3：
```bash
pip3 install -r requirements.txt
```

### 3. 設定權限
確保 Python 腳本有執行權限：
```bash
chmod +x main.py
chmod +x prowavedaq.py
chmod +x csv_writer.py
```

### 4. 設定串列埠權限（Linux）
如果使用 USB 轉串列埠設備，可能需要將使用者加入 dialout 群組：
```bash
sudo usermod -a -G dialout $USER
```
然後重新登入或執行：
```bash
newgrp dialout
```

### 5. 確認設定檔
檢查 `API/` 目錄下的設定檔：
- `API/ProWaveDAQ.ini` - ProWaveDAQ 設備設定
- `API/Master.ini` - 儲存設定

## 使用說明

### 啟動系統

執行主程式：
```bash
python3 main.py
```

或直接執行：
```bash
./main.py
```

或是執行：
```bash
./run.sh
```
直接進入虛擬環境並啟動程式

啟動成功後，您會看到類似以下的訊息：
```
============================================================
ProWaveDAQ Real-time Data Visualization System
============================================================
Web interface will be available at http://0.0.0.0:8080/
Press Ctrl+C to stop the server
============================================================
```

### 使用 Web 介面

1. **開啟瀏覽器**
   - 在本地機器：開啟 `http://localhost:8080/`
   - 在遠端機器：開啟 `http://<設備IP>:8080/`

2. **輸入資料標籤**
   - 在「資料標籤 (Label)」欄位輸入本次測量的標籤名稱
   - 例如：`test_001`、`vibration_20240101` 等

3. **開始資料收集**
   - 點擊「開始讀取」按鈕
   - 系統會自動：
     - 連接 ProWaveDAQ 設備
     - 開始讀取資料
     - 即時顯示資料曲線
     - 自動儲存 CSV 檔案

4. **查看即時資料**
   - 即時曲線圖會自動更新（每 200ms）
   - 可以同時查看三個通道的資料
   - 資料點數會即時顯示

5. **停止資料收集**
   - 點擊「停止讀取」按鈕
   - 系統會安全地停止採集並關閉連線

6. **管理設定檔**
   - 點擊「設定檔管理」連結
   - 可以編輯 `ProWaveDAQ.ini` 和 `Master.ini`
   - 修改後點擊「儲存設定檔」

7. **瀏覽和下載檔案**
   - 點擊「檔案瀏覽」連結
   - 可以瀏覽 `output/ProWaveDAQ/` 目錄中的所有資料夾和檔案
   - 點擊資料夾名稱或「進入」按鈕可以進入資料夾
   - 點擊「下載」按鈕可以下載 CSV 檔案
   - 使用麵包屑導航可以返回上層目錄

### 設定檔說明

#### ProWaveDAQ.ini
```ini
[ProWaveDAQ]
serialPort = /dev/ttyUSB0    # 串列埠路徑
baudRate = 3000000           # 鮑率
sampleRate = 7812            # 取樣率（Hz）
slaveID = 1                  # Modbus 從站 ID
```

#### Master.ini
```ini
[SaveUnit]
second = 5                   # 每個 CSV 檔案的資料時間長度（秒）
```

**分檔邏輯說明**：
- 系統會根據 `sampleRate × channels × second` 計算每個檔案應包含的資料點數
- 當累積的資料點數達到目標值時，自動建立新檔案
- 例如：取樣率 7812 Hz，3 通道，5 秒 → 每個檔案約 117,180 個資料點

### 輸出檔案

CSV 檔案會儲存在 `output/ProWaveDAQ/` 目錄下，檔案命名格式：
```
YYYYMMDDHHMMSS_<Label>_001.csv
YYYYMMDDHHMMSS_<Label>_002.csv
...
```

每個 CSV 檔案包含：
- `Timestamp` - 時間戳記
- `Channel_1` - 通道 1 資料
- `Channel_2` - 通道 2 資料
- `Channel_3` - 通道 3 資料

## 檔案架構

```
ProWaveDAQ_Python_Visualization_Unit/
│
├── API/
│   ├── ProWaveDAQ.ini      # ProWaveDAQ 設備設定檔
│   └── Master.ini           # 儲存設定檔
│
├── output/
│   └── ProWaveDAQ/         # CSV 輸出目錄
│       └── YYYYMMDDHHMMSS_<Label>_*.csv
│
├── prowavedaq.py            # ProWaveDAQ 核心模組（Modbus 通訊）
├── csv_writer.py            # CSV 寫入器模組
├── main.py                  # 主控制程式（Web 介面）
├── requirements.txt         # Python 依賴套件列表
├── README.md                # 本文件
├── CURSOR.md                # 開發需求文件
├── deploy.sh                # 部署腳本
├── run.sh                   # 啟動腳本（進入虛擬環境並啟動程式）
└── templates/               # HTML 模板目錄
    ├── index.html           # 主頁模板
    ├── config.html          # 設定檔管理頁面模板
    └── files.html           # 檔案瀏覽頁面模板
```

## API 路由說明

| 路由 | 方法 | 功能說明 |
|------|------|----------|
| `/` | GET | 主頁，顯示設定表單、Label 輸入、開始/停止按鈕與折線圖 |
| `/data` | GET | 回傳目前最新資料 JSON 給前端 |
| `/status` | GET | 檢查資料收集狀態 |
| `/config` | GET | 顯示設定檔編輯頁面 |
| `/config` | POST | 儲存修改後的設定檔 |
| `/start` | POST | 啟動 DAQ、CSVWriter 與即時顯示 |
| `/stop` | POST | 停止所有執行緒、安全關閉 |
| `/files_page` | GET | 檔案瀏覽頁面 |
| `/files` | GET | 列出 output 目錄中的檔案和資料夾（查詢參數：path） |
| `/download` | GET | 下載檔案（查詢參數：path） |

### API 回應格式

#### `/data` (GET)
```json
{
  "success": true,
  "data": [0.123, 0.456, 0.789, ...],
  "counter": 12345
}
```

#### `/start` (POST)
請求：
```json
{
  "label": "test_001"
}
```

回應：
```json
{
  "success": true,
  "message": "資料收集已啟動 (取樣率: 7812 Hz, 分檔間隔: 5 秒)"
}
```

**注意**：API 回應訊息目前為中文，但系統啟動訊息為英文。

#### `/stop` (POST)
回應：
```json
{
  "success": true,
  "message": "資料收集已停止"
}
```

#### `/status` (GET)
回應：
```json
{
  "success": true,
  "is_collecting": true,
  "counter": 12345
}
```

#### `/files` (GET)
查詢參數：
- `path` (可選)：要瀏覽的子目錄路徑

回應：
```json
{
  "success": true,
  "items": [
    {
      "name": "20240101120000_test_001",
      "type": "directory",
      "path": "20240101120000_test_001"
    },
    {
      "name": "data.csv",
      "type": "file",
      "path": "data.csv",
      "size": 1024
    }
  ],
  "current_path": ""
}
```

#### `/download` (GET)
查詢參數：
- `path` (必需)：要下載的檔案路徑

回應：直接下載檔案

## 故障排除

### 常見問題

#### 1. 無法連接設備
**症狀**：啟動後無法讀取資料

**解決方法**：
- 檢查串列埠路徑是否正確（`/dev/ttyUSB0` 或其他）
- 確認設備已正確連接
- 檢查使用者是否有串列埠存取權限
- 嘗試使用 `ls -l /dev/ttyUSB*` 確認設備存在

#### 2. Web 介面無法開啟
**症狀**：無法在瀏覽器中開啟網頁

**解決方法**：
- 確認防火牆允許 8080 埠
- 檢查是否有其他程式佔用 8080 埠
- 確認 Python 程式正在執行
- 檢查系統日誌是否有錯誤訊息

#### 3. 資料顯示不正確
**症狀**：圖表顯示異常或資料點不正確

**解決方法**：
- 檢查設定檔中的取樣率是否正確
- 確認通道數設定（預設為 3）
- 檢查瀏覽器控制台是否有 JavaScript 錯誤

#### 4. CSV 檔案未產生
**症狀**：資料收集正常但沒有 CSV 檔案

**解決方法**：
- 檢查 `output/ProWaveDAQ/` 目錄是否有寫入權限
- 確認 Label 已正確輸入
- 檢查磁碟空間是否充足

#### 5. 資料採集停止
**症狀**：資料採集中途停止

**解決方法**：
- 檢查 Modbus 連線是否中斷
- 查看終端機的錯誤訊息
- 確認設備是否正常運作

### 除錯模式

如需查看詳細的除錯資訊，可以修改程式碼中的 `print` 語句，或使用 Python 的日誌模組。

## 技術架構

### 執行緒設計

| 執行緒 | 功能 | 備註 |
|--------|------|------|
| 主執行緒 | 控制流程、讀取資料、推送到 CSV 與 Web | 同步主控核心 |
| Flask Thread | 提供 HTTP 介面與 `/data` API | daemon=True |
| Collection Thread | 資料收集迴圈 | 在 `/start` 時啟動 |

### 資料流

```
ProWaveDAQ 設備
    ↓ (Modbus RTU)
ProWaveDAQ 類別 (prowavedaq.py)
    ↓ (資料佇列)
主程式 (main.py)
    ├──→ 即時顯示 (記憶體變數)
    │       ↓
    │   Flask /data API
    │       ↓
    │   前端 Chart.js (templates/index.html)
    │
    └──→ CSV 儲存 (csv_writer.py)
            ↓
        CSV 檔案
```

### 技術限制

- 不使用 `asyncio` 或 `WebSocket`
- 不使用檔案中介資料交換
- 所有資料傳遞均在記憶體中完成
- 使用 Python 變數或全域狀態保存資料

## 開發說明

### 擴展功能

如需擴展系統功能，可以：

1. **修改前端介面**：編輯 `templates/index.html` 和 `templates/config.html` 模板
2. **調整圖表設定**：在 `templates/index.html` 中修改 Chart.js 的配置選項
3. **新增 API 路由**：在 `main.py` 中新增路由處理函數
4. **自訂 CSV 格式**：修改 `csv_writer.py` 中的寫入邏輯

### 程式碼結構

- `prowavedaq.py`：負責 Modbus RTU 通訊與資料讀取
- `csv_writer.py`：負責 CSV 檔案的建立與寫入
- `main.py`：整合所有功能，提供 Web 介面（使用 Flask + templates）
- `templates/index.html`：主頁 HTML 模板（包含 Chart.js 圖表）
- `templates/config.html`：設定檔管理頁面模板

## 授權資訊

本專案為內部使用專案，請遵循相關使用規範。

## 聯絡資訊

如有問題或建議，請聯絡專案維護者。

## 更新日誌

### Version 1.0.0
- 初始版本發布
- 實現基本的即時資料採集與可視化功能
- Web 介面控制
- 自動 CSV 分檔儲存

### Version 1.0.1
- 將 HTML 部分改為模板以簡化 Python 程式碼整潔性

### Version 1.0.2
- 修復：讀取中進入 config 頁面再回到主畫面時，狀態會自動恢復
- 新增：檔案瀏覽功能，可瀏覽 output 目錄中的資料夾和檔案
- 新增：檔案下載功能

---

**最後更新**：2025年11月06日
**作者**：王建葦