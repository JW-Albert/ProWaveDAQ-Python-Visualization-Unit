#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProWaveDAQ 設備通訊模組

負責與 ProWaveDAQ 設備進行 Modbus RTU 通訊，支援智慧讀取邏輯和高效能資料採集。
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
    """ProWaveDAQ 設備通訊類別"""
    
    REG_SAMPLE_RATE = 0x01
    REG_FIFO_STATUS = 0x02
    MAX_READ_WORDS = 123
    CHANNELS = 3

    def __init__(self):
        self.serial_port = "/dev/ttyUSB0"
        self.baud_rate = 3_000_000
        self.sample_rate = 7812
        self.slave_id = 1

        self.client: Optional[ModbusSerialClient] = None
        self.reading = False
        self.thread: Optional[threading.Thread] = None
        self.queue: "queue.Queue[List[float]]" = queue.Queue(maxsize=50000)
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
        """清空硬體緩衝區，避免啟動時延遲"""
        info("Flushing hardware buffer (clearing old data)...")
        dropped_packets = 0
        try:
            for _ in range(500):
                size = self._read_fifo_size()
                if size < 100:
                    break
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
        """極速讀取迴圈，使用本地快取減少 Modbus 通訊"""
        debug("Read loop started (Optimized G.py Logic)")
        self.cached_buffer_size = 0

        while self.reading:
            try:
                if self.cached_buffer_size == 0:
                    self.cached_buffer_size = self._read_fifo_size()
                    if self.cached_buffer_size == 0:
                        time.sleep(0.001)
                        continue

                count_to_read = min(self.cached_buffer_size, self.MAX_READ_WORDS)
                count_to_read = (count_to_read // self.CHANNELS) * self.CHANNELS
                
                if count_to_read == 0:
                    self.cached_buffer_size = 0
                    continue

                r = self.client.read_input_registers(
                    address=self.REG_FIFO_STATUS, 
                    count=count_to_read + 1
                )
                
                if r.isError() or not r.registers:
                    self.cached_buffer_size = 0
                    continue
                
                self.cached_buffer_size = r.registers[0]
                payload = r.registers[1:]
                samples = self._convert_to_float(payload)
                if samples:
                    self._push(samples)

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
        """將資料推入佇列，佇列滿時丟棄最舊資料"""
        try:
            self.queue.put_nowait(data)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(data)
            except queue.Empty:
                pass
