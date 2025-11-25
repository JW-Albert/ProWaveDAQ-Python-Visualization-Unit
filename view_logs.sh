#!/bin/bash
# 查看日誌的便捷腳本

LOG_DIR="logs"

if [ ! -d "${LOG_DIR}" ]; then
    echo "日誌目錄不存在: ${LOG_DIR}"
    echo "請先執行程式以產生日誌檔案"
    exit 1
fi

# 找出最新的日誌檔案
LATEST_LOG=$(ls -t ${LOG_DIR}/app_*.log 2>/dev/null | head -1)

if [ -z "${LATEST_LOG}" ]; then
    echo "找不到日誌檔案"
    exit 1
fi

echo "查看日誌: ${LATEST_LOG}"
echo "按 Ctrl+C 停止查看"
echo "============================================================"
echo ""

# 根據參數決定查看方式
case "$1" in
    -e|--error)
        # 只查看錯誤訊息
        tail -f ${LATEST_LOG} | grep --line-buffered "\[Error\]"
        ;;
    -w|--warning)
        # 只查看警告訊息
        tail -f ${LATEST_LOG} | grep --line-buffered "\[Warning\]"
        ;;
    -i|--info)
        # 只查看 INFO 訊息
        tail -f ${LATEST_LOG} | grep --line-buffered "\[INFO\]"
        ;;
    -d|--debug)
        # 只查看 Debug 訊息
        tail -f ${LATEST_LOG} | grep --line-buffered "\[Debug\]"
        ;;
    -n|--lines)
        # 查看最後 N 行
        if [ -z "$2" ]; then
            echo "請指定行數，例如: $0 -n 100"
            exit 1
        fi
        tail -n $2 ${LATEST_LOG}
        ;;
    *)
        # 預設：查看所有日誌
        tail -f ${LATEST_LOG}
        ;;
esac