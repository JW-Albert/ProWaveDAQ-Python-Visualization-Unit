#!/bin/bash
# ProWaveDAQ Python Version Auto Deployment Script
# This script automatically sets up the development environment and necessary system permissions

set -e  # Exit immediately if a command exits with a non-zero status

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ProWaveDAQ Python Version Auto Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check and install Python packages
echo -e "${YELLOW}[1/6] Checking and installing Python packages...${NC}"

# Check if Debian/Ubuntu system
if command -v apt-get &> /dev/null; then
    # Check if Python needs to be installed
    if ! command -v python3 &> /dev/null; then
        echo "Installing python3..."
        if [ "$EUID" -eq 0 ]; then
            apt-get update -qq
            apt-get install -y python3 python3-pip python3-venv
        else
            echo -e "${YELLOW}sudo privileges required to install Python packages${NC}"
            echo "Please run: sudo $0"
            exit 1
        fi
    fi
    
    # Check pip3
    if ! command -v pip3 &> /dev/null; then
        echo "Installing python3-pip..."
        if [ "$EUID" -eq 0 ]; then
            apt-get install -y python3-pip
        else
            echo -e "${YELLOW}sudo privileges required to install pip${NC}"
            echo "Please run: sudo $0"
            exit 1
        fi
    fi
    
    # Check venv module
    if ! python3 -c "import venv" 2>/dev/null; then
        echo "Installing python3-venv..."
        if [ "$EUID" -eq 0 ]; then
            apt-get install -y python3-venv
        else
            echo -e "${YELLOW}sudo privileges required to install venv${NC}"
            echo "Please run: sudo $0"
            exit 1
        fi
    fi
elif command -v yum &> /dev/null; then
    # CentOS/RHEL system
    if ! command -v python3 &> /dev/null; then
        echo "Installing python3..."
        if [ "$EUID" -eq 0 ]; then
            yum install -y python3 python3-pip
        else
            echo -e "${YELLOW}sudo privileges required to install Python packages${NC}"
            echo "Please run: sudo $0"
            exit 1
        fi
    fi
else
    # Other systems, only check without auto-installation
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: python3 command not found${NC}"
        echo "Please manually install Python 3.10 or higher"
        exit 1
    fi
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}Python version: $PYTHON_VERSION${NC}"
echo ""

# Check if virtual environment needs to be created
echo -e "${YELLOW}[2/6] Setting up Python virtual environment...${NC}"
if [ -d "venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf venv
    echo -e "${GREEN} Old virtual environment removed${NC}"
fi
echo "Creating virtual environment..."
python3 -m venv venv
echo -e "${GREEN} Virtual environment created${NC}"

# Activate virtual environment and install dependencies
echo -e "${YELLOW}[3/6] Installing dependencies...${NC}"
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet

# Install dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing packages from requirements.txt..."
    pip install -r requirements.txt
    echo -e "${GREEN} Dependencies installed successfully${NC}"
else
    echo -e "${RED}Warning: requirements.txt not found${NC}"
fi

echo ""

# Check and set serial port permissions
echo -e "${YELLOW}[4/6] Setting serial port permissions...${NC}"
CURRENT_USER=${SUDO_USER:-$USER}

if [ "$EUID" -eq 0 ]; then
    # When running with sudo
    if groups "$CURRENT_USER" | grep -q "\bdialout\b"; then
        echo -e "${GREEN} User $CURRENT_USER is already in dialout group${NC}"
    else
        echo "Adding user $CURRENT_USER to dialout group..."
        usermod -aG dialout "$CURRENT_USER"
        echo -e "${GREEN} User added to dialout group${NC}"
        echo -e "${YELLOW}Note: Please log out and log in again, or reboot the system for permissions to take effect${NC}"
    fi
else
    # When running without sudo
    if groups | grep -q "\bdialout\b"; then
        echo -e "${GREEN}Current user is already in dialout group${NC}"
    else
        echo -e "${YELLOW}sudo privileges required to set serial port permissions${NC}"
        echo "Please run: sudo $0"
        echo "Or manually run: sudo usermod -aG dialout $USER"
    fi
fi

echo ""

# Verify installation
echo -e "${YELLOW}[5/6] Verifying installation...${NC}"

# Check pymodbus
if python3 -c "from pymodbus.client import ModbusSerialClient" 2>/dev/null; then
    echo -e "${GREEN} pymodbus installed successfully${NC}"
else
    echo -e "${RED} pymodbus installation failed${NC}"
    echo "Please manually run: pip install pymodbus>=3.11.3"
fi

# Check pyserial
if python3 -c "import serial" 2>/dev/null; then
    echo -e "${GREEN} pyserial installed successfully${NC}"
else
    echo -e "${RED} pyserial installation failed${NC}"
    echo "Please manually run: pip install pyserial>=3.5"
fi

# Check configuration files
echo -e "${YELLOW}[6/6] Checking configuration files...${NC}"
if [ -f "API/ProWaveDAQ.ini" ]; then
    echo -e "${GREEN}Found ProWaveDAQ.ini${NC}"
else
    echo -e "${YELLOW}Warning: API/ProWaveDAQ.ini not found${NC}"
fi

if [ -f "API/Master.ini" ]; then
    echo -e "${GREEN}Found Master.ini${NC}"
else
    echo -e "${YELLOW}Warning: API/Master.ini not found${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Deployment completed!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. If dialout group was just configured, please log out and log in again"
echo "2. Start the program:"
echo "   cd $SCRIPT_DIR"
echo "   source venv/bin/activate"
echo "   python3 main.py"
echo ""
echo "   Or use the run script:"
echo "   ./run.sh"
echo ""
echo "For help, please refer to README.md"
