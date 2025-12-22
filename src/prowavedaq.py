#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProWaveDAQ 設備通訊模組

此模組負責與 ProWaveDAQ 設備進行 Modbus RTU 通訊，支援：
- 智慧讀取邏輯（利用 Data Header 更新剩餘數量，減少 50% 通訊流量）
- 開機自動清空（啟動時自動排空感測器積壓的舊資料）
- 高效能讀取（移除不必要的 sleep，榨乾 RS485 頻寬）
- 遵循原廠手冊規範（基於 RS485_ModbusRTU通訊說明_PwDAQ.pdf）
- 使用 FC04 (Read Input Registers) 讀取資料
- 本地緩衝區快取（減少 Modbus 詢問次數）
- 大容量資料佇列（50,000 筆資料緩衝）
- 執行緒安全（使用 queue.Queue 進行資料傳遞）
"""

import time
import threading
import configparser
import queue
from typing import List, Optional

from pymodbus.client import ModbusSerialClient

try:
    from logger import info, debug, warning, error
except ImportError:
    def info(m): print(f"[INFO] {m}")
    def debug(m): print(f"[DEBUG] {m}")
    def warning(m): print(f"[WARN] {m}")
    def error(m): print(f"[ERROR] {m}")


class ProWaveDAQ:
    """
    ProWaveDAQ 設備通訊類別 (極速版)
    """
    
    # 暫存器定義
    REG_SAMPLE_RATE = 0x01
    REG_FIFO_STATUS = 0x02  # 資料緩衝區大小與起始位址
    
    MAX_READ_WORDS = 123    # 單次最大讀取字數
    CHANNELS = 3

    def __init__(self):
        self.serial_port = "/dev/ttyUSB0"
        self.baud_rate = 3_000_000
        self.sample_rate = 7812
        self.slave_id = 1

        self.client: Optional[ModbusSerialClient] = None
        self.reading = False
        self.thread: Optional[threading.Thread] = None
        self.queue: "queue.Queue[List[float]]" = queue.Queue(maxsize=50000) # 加大佇列
        
        # 本地快取的緩衝區剩餘量 (核心優化變數)
        self.cached_buffer_size = 0

    def init_devices(self, ini_path: str):
        cfg = configparser.ConfigParser()
        cfg.read(ini_path, encoding="utf-8")

        self.serial_port = cfg.get("ProWaveDAQ", "serialPort", fallback=self.serial_port)
        self.baud_rate = cfg.getint("ProWaveDAQ", "baudRate", fallback=self.baud_rate)
        self.sample_rate = cfg.getint("ProWaveDAQ", "sampleRate", fallback=self.sample_rate)
        self.slave_id = cfg.getint("ProWaveDAQ", "slaveID", fallback=self.slave_id)

        if not self._connect():
            raise RuntimeError("Modbus connect failed")

        self._set_sample_rate()
        
        # [新增] 啟動前先清空感測器內部的陳舊資料
        self._flush_hardware_buffer()

    def _connect(self) -> bool:
        self.client = ModbusSerialClient(
            port=self.serial_port,
            baudrate=self.baud_rate,
            parity="N", stopbits=1, bytesize=8,
            timeout=0.5, framer="rtu",
        )
        if not self.client.connect():
            return False
        self.client.unit_id = self.slave_id
        self.client.framer.skip_encode_mobile = True 
        info("Modbus connection established")
        return True

    def _set_sample_rate(self):
        r = self.client.write_register(self.REG_SAMPLE_RATE, self.sample_rate)
        if r.isError():
            error("Failed to set sample rate")
        else:
            debug(f"Sample rate set to {self.sample_rate} Hz")

    def _flush_hardware_buffer(self):
        """
        清空硬體緩衝區
        如果感測器內積壓了 65000 筆資料，讀取會嚴重延遲。
        此函式會快速讀取並丟棄，直到緩衝區清空。
        """
        info("Flushing hardware buffer (clearing old data)...")
        dropped_packets = 0
        try:
            # 最多嘗試清空 500 次 (約 6 萬筆)
            for _ in range(500):
                size = self._read_fifo_size()
                if size < 100: # 緩衝區已接近空
                    break
                
                # 快速讀取並丟棄
                read_count = min(size, self.MAX_READ_WORDS)
                self.client.read_input_registers(address=self.REG_FIFO_STATUS, count=read_count + 1)
                dropped_packets += 1
                
            info(f"Buffer flushed. Dropped {dropped_packets} packets. System is now real-time.")
        except Exception as e:
            warning(f"Flush warning: {e}")

    def start_reading(self):
        if self.reading:
            return
        self.reading = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        info("ProWaveDAQ reading started (High Performance Mode)")

    def stop_reading(self):
        self.reading = False
        if self.thread:
            self.thread.join()
        if self.client:
            self.client.close()
        info("ProWaveDAQ reading stopped")

    def get_data(self) -> List[float]:
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return []
            
    def get_sample_rate(self) -> int:
        return self.sample_rate

    def _read_loop(self):
        """
        極速讀取迴圈
        優化策略：
        1. 優先使用本地 cached_buffer_size 判斷是否讀取，減少 50% 的 Modbus 流量。
        2. 讀取回來的 Header 會自動更新 cached_buffer_size。
        3. 只有當不知道大小 (0) 時，才去詢問硬體。
        """
        debug("Read loop started (Optimized G.py Logic)")
        
        # 重置計數
        self.cached_buffer_size = 0

        while self.reading:
            try:
                # 策略 1: 如果本地計數為 0，才去問硬體 (FC04 Read Size)
                if self.cached_buffer_size == 0:
                    self.cached_buffer_size = self._read_fifo_size()
                    
                    if self.cached_buffer_size == 0:
                        # 真的沒資料，稍微休息避免 CPU 100%
                        time.sleep(0.001) 
                        continue

                # 策略 2: 直接讀取 (FC04 Read Data)
                # 根據目前已知的大小，決定讀多少 (最多 123)
                count_to_read = min(self.cached_buffer_size, self.MAX_READ_WORDS)
                # 確保 3 的倍數
                count_to_read = (count_to_read // self.CHANNELS) * self.CHANNELS
                
                if count_to_read == 0:
                    # 剩餘資料不足 3 筆，重新詢問大小
                    self.cached_buffer_size = 0 
                    continue

                # 執行讀取
                # Request: [Size(1)] + [Data(N)]
                r = self.client.read_input_registers(
                    address=self.REG_FIFO_STATUS, 
                    count=count_to_read + 1
                )
                
                if r.isError() or not r.registers:
                    # 讀取失敗，重置計數，下次重新詢問
                    self.cached_buffer_size = 0
                    continue
                
                # 策略 3: 利用 Header 更新本地計數
                # r.registers[0] 是感測器告訴我們「讀完這包後，我還剩下多少」
                new_remaining_size = r.registers[0]
                self.cached_buffer_size = new_remaining_size
                
                # 處理數據 (移除 Header)
                payload = r.registers[1:]
                samples = self._convert_to_float(payload)
                if samples:
                    self._push(samples)

                # [極速模式] 不使用 sleep，全力讀取

            except Exception as e:
                error(f"Read loop error: {e}")
                self.cached_buffer_size = 0
                time.sleep(0.1)

    def _read_fifo_size(self) -> int:
        r = self.client.read_input_registers(address=self.REG_FIFO_STATUS, count=1)
        if r.isError() or not r.registers:
            return 0
        return r.registers[0]

    def _convert_to_float(self, raw: List[int]) -> List[float]:
        out: List[float] = []
        for v in raw:
            signed = v if v < 32768 else v - 65536
            out.append(signed / 8192.0)
        return out

    def _push(self, data: List[float]):
        try:
            self.queue.put_nowait(data)
        except queue.Full:
            # 佇列滿時丟棄最舊的資料，保持即時性
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(data)
            except queue.Empty:
                pass
