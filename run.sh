#!/bin/bash

sudo bash -c "echo 1 > /sys/bus/usb-serial/devices/ttyUSB0/latency_timer"

clear && echo "Starting ProWaveDAQ Real-time Data Visualization System..." && echo "Press Ctrl+C to stop the server" && echo "Web interface will be available at http://0.0.0.0:8080/" && echo "================================================" && echo ""
source venv/bin/activate
python src/main.py