#!/bin/bash
# 啟動程式並將日誌保存到檔案

sudo bash -c "echo 1 > /sys/bus/usb-serial/devices/ttyUSB0/latency_timer"

# 建立日誌目錄
LOG_DIR="logs"
mkdir -p ${LOG_DIR}

# 產生帶時間戳記的日誌檔名
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/app_${TIMESTAMP}.log"

echo "============================================================"
echo "ProWaveDAQ Real-time Data Visualization System"
echo "============================================================"
echo "日誌將保存到: ${LOG_FILE}"
echo "使用 'tail -f ${LOG_FILE}' 查看即時日誌"
echo "使用 'tail -f ${LOG_FILE} | grep Error' 查看錯誤訊息"
echo "============================================================"
echo ""

# 啟動程式並將所有輸出（包含錯誤）保存到日誌檔案
# 同時使用 tee 在終端機顯示
source venv/bin/activate
python src/main.py 2>&1 | tee ${LOG_FILE}

