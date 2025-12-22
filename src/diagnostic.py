#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
感測器硬體診斷工具 (diagnostic.py)
用途：直接讀取 Modbus 原始數值，排除網頁與佇列的影響，確認感測器狀態。
"""
import time
from pymodbus.client import ModbusSerialClient
import struct

# ================= 設定區 =================
PORT = "/dev/ttyUSB0"
BAUDRATE = 3000000
SLAVE_ID = 1
# =========================================

def test_sensor():
    print(f"正在連接感測器 {PORT} @ {BAUDRATE}...")
    client = ModbusSerialClient(
        port=PORT,
        baudrate=BAUDRATE,
        parity="N", stopbits=1, bytesize=8,
        timeout=1
    )
    
    if not client.connect():
        print("❌ 無法連接 Modbus，請檢查 USB 連線或權限 (sudo)。")
        return

    # 設定預設 Slave ID (解決 TypeError 問題)
    client.unit_id = SLAVE_ID

    print("✅ 連線成功！開始讀取數據...\n")
    print(f"{'Header':<8} | {'Raw X':<8} {'Raw Y':<8} {'Raw Z':<8} | {'G-Val X':<8} {'G-Val Y':<8} {'G-Val Z':<8}")
    print("-" * 70)

    try:
        while True:
            # 1. 讀取 FIFO 大小 (Addr: 0x02)
            # 修正：移除 slave=... 參數，改用 client.unit_id
            rr = client.read_input_registers(address=0x02, count=1)
            
            if rr.isError():
                print("Read Error (Size)")
                time.sleep(0.1)
                continue
            
            size = rr.registers[0]
            if size == 0:
                continue

            # 2. 讀取數據 (Addr: 0x02, Count: Size + 1)
            # 限制讀取長度以免超時
            read_len = min(size, 120)
            # 確保是 3 的倍數
            read_len = (read_len // 3) * 3
            
            if read_len == 0:
                continue

            # 修正：移除 slave=... 參數
            rr_data = client.read_input_registers(address=0x02, count=read_len + 1)
            
            if rr_data.isError():
                print("Read Error (Data)")
                continue

            # raw_packet[0] 是 Header (應與 size 接近)
            # raw_packet[1:] 是數據
            header_val = rr_data.registers[0]
            payload = rr_data.registers[1:]

            # 只顯示第一組 XYZ，方便人類閱讀
            if len(payload) >= 3:
                raw_x = payload[0]
                raw_y = payload[1]
                raw_z = payload[2]

                # 轉換為 Signed 16-bit
                sx = raw_x if raw_x < 32768 else raw_x - 65536
                sy = raw_y if raw_y < 32768 else raw_y - 65536
                sz = raw_z if raw_z < 32768 else raw_z - 65536

                # 轉換為 G 值 (假設 8192 = 1G)
                gx = sx / 8192.0
                gy = sy / 8192.0
                gz = sz / 8192.0

                print(f"Size:{header_val:<3} | {raw_x:<8} {raw_y:<8} {raw_z:<8} | {gx:<8.3f} {gy:<8.3f} {gz:<8.3f}")

            # 慢一點，讓人眼看得到數值
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n停止測試")
        client.close()

if __name__ == "__main__":
    test_sensor()