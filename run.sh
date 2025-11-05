#!/bin/bash

clear && echo "Starting ProWaveDAQ Real-time Data Visualization System..." && echo "Press Ctrl+C to stop the server" && echo "Web interface will be available at http://0.0.0.0:8080/" && echo "================================================" && echo ""
source venv/bin/activate
python main.py