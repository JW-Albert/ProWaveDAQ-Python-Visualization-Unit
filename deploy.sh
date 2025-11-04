#!/bin/bash
# ProWaveDAQ Python 版本自動部署腳本
# 此腳本會自動設定開發環境和必要的系統權限

set -e  # 遇到錯誤時立即退出

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 取得腳本所在目錄
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ProWaveDAQ Python 版本自動部署${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 檢查並安裝 Python 相關套件
echo -e "${YELLOW}[1/6] 檢查並安裝 Python 相關套件...${NC}"

# 檢查是否為 Debian/Ubuntu 系統
if command -v apt-get &> /dev/null; then
    # 檢查是否需要安裝 Python
    if ! command -v python3 &> /dev/null; then
        echo "正在安裝 python3..."
        if [ "$EUID" -eq 0 ]; then
            apt-get update -qq
            apt-get install -y python3 python3-pip python3-venv
        else
            echo -e "${YELLOW}需要 sudo 權限以安裝 Python 套件${NC}"
            echo "請執行：sudo $0"
            exit 1
        fi
    fi
    
    # 檢查 pip3
    if ! command -v pip3 &> /dev/null; then
        echo "正在安裝 python3-pip..."
        if [ "$EUID" -eq 0 ]; then
            apt-get install -y python3-pip
        else
            echo -e "${YELLOW}需要 sudo 權限以安裝 pip${NC}"
            echo "請執行：sudo $0"
            exit 1
        fi
    fi
    
    # 檢查 venv 模組
    if ! python3 -c "import venv" 2>/dev/null; then
        echo "正在安裝 python3-venv..."
        if [ "$EUID" -eq 0 ]; then
            apt-get install -y python3-venv
        else
            echo -e "${YELLOW}需要 sudo 權限以安裝 venv${NC}"
            echo "請執行：sudo $0"
            exit 1
        fi
    fi
elif command -v yum &> /dev/null; then
    # CentOS/RHEL 系統
    if ! command -v python3 &> /dev/null; then
        echo "正在安裝 python3..."
        if [ "$EUID" -eq 0 ]; then
            yum install -y python3 python3-pip
        else
            echo -e "${YELLOW}需要 sudo 權限以安裝 Python 套件${NC}"
            echo "請執行：sudo $0"
            exit 1
        fi
    fi
else
    # 其他系統，只檢查不自動安裝
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}錯誤：找不到 python3 命令${NC}"
        echo "請手動安裝 Python 3.10 或更高版本"
        exit 1
    fi
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}Python 版本: $PYTHON_VERSION${NC}"
echo ""

# 檢查是否需要建立虛擬環境
echo -e "${YELLOW}[2/6] 設定 Python 虛擬環境...${NC}"
if [ ! -d "venv" ]; then
    echo "建立虛擬環境中..."
    python3 -m venv venv
    echo -e "${GREEN} 虛擬環境已建立${NC}"
else
    echo -e "${GREEN} 虛擬環境已存在${NC}"
fi

# 啟動虛擬環境並安裝依賴
echo -e "${YELLOW}[3/6] 安裝依賴套件...${NC}"
source venv/bin/activate

# 升級 pip
echo "升級 pip..."
pip install --upgrade pip --quiet

# 安裝依賴套件
if [ -f "requirements.txt" ]; then
    echo "安裝 requirements.txt 中的套件..."
    pip install -r requirements.txt
    echo -e "${GREEN} 依賴套件安裝完成${NC}"
else
    echo -e "${RED}警告：找不到 requirements.txt${NC}"
fi

echo ""

# 檢查並設定串列埠權限
echo -e "${YELLOW}[4/6] 設定串列埠權限...${NC}"
CURRENT_USER=${SUDO_USER:-$USER}

if [ "$EUID" -eq 0 ]; then
    # 使用 sudo 執行時
    if groups "$CURRENT_USER" | grep -q "\bdialout\b"; then
        echo -e "${GREEN} 用戶 $CURRENT_USER 已在 dialout 群組中${NC}"
    else
        echo "將用戶 $CURRENT_USER 加入 dialout 群組..."
        usermod -aG dialout "$CURRENT_USER"
        echo -e "${GREEN} 用戶已加入 dialout 群組${NC}"
        echo -e "${YELLOW}注意：請登出並重新登入系統，或重新啟動系統，權限才會生效${NC}"
    fi
else
    # 未使用 sudo 執行時
    if groups | grep -q "\bdialout\b"; then
        echo -e "${GREEN}當前用戶已在 dialout 群組中${NC}"
    else
        echo -e "${YELLOW}需要 sudo 權限以設定串列埠權限${NC}"
        echo "請執行：sudo $0"
        echo "或手動執行：sudo usermod -aG dialout $USER"
    fi
fi

echo ""

# 驗證安裝
echo -e "${YELLOW}[5/6] 驗證安裝...${NC}"

# 檢查 pymodbus
if python3 -c "from pymodbus.client import ModbusSerialClient" 2>/dev/null; then
    echo -e "${GREEN} pymodbus 安裝成功${NC}"
else
    echo -e "${RED} pymodbus 安裝失敗${NC}"
    echo "請手動執行：pip install pymodbus>=3.11.3"
fi

# 檢查 pyserial
if python3 -c "import serial" 2>/dev/null; then
    echo -e "${GREEN} pyserial 安裝成功${NC}"
else
    echo -e "${RED} pyserial 安裝失敗${NC}"
    echo "請手動執行：pip install pyserial>=3.5"
fi

# 檢查設定檔案
echo -e "${YELLOW}[6/6] 檢查設定檔案...${NC}"
if [ -f "API/ProWaveDAQ.ini" ]; then
    echo -e "${GREEN}找到 ProWaveDAQ.ini${NC}"
else
    echo -e "${YELLOW}警告：找不到 API/ProWaveDAQ.ini${NC}"
fi

if [ -f "API/Master.ini" ]; then
    echo -e "${GREEN}找到 Master.ini${NC}"
else
    echo -e "${YELLOW}警告：找不到 API/Master.ini${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}部署完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "接下來的步驟："
echo "1. 如果剛才設定了 dialout 群組，請登出並重新登入系統"
echo "2. 啟動程式："
echo "   cd $SCRIPT_DIR"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo "如需幫助，請參閱 README.md"