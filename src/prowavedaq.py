#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProWaveDAQ Python版本
振動數據採集系統 - 使用Modbus RTU通訊協議

設計目標：
- 對外 API 與原本版本相容（給 main / 前端用）
- 讀取流程模組化，方便未來調整
- 確保 X/Y/Z 通道不會錯位：每次讀取只處理「當次完整的 XYZ 三軸組」
"""

import re
import time
import threading
import configparser
from typing import List, Optional
import glob
import sys
import queue

try:
    # pymodbus 3.6.0+ 的新 import 路徑
    from pymodbus.client import ModbusSerialClient
except ImportError:
    print("Error: Unable to find compatible pymodbus version")
    print("Please ensure pymodbus is installed: pip install pymodbus>=3.6.0")
    print("Or try reinstalling: pip uninstall pymodbus && pip install pymodbus>=3.6.0")
    sys.exit(1)

# 日誌系統（可接你的 logger.py）
try:
    from logger import info, debug, error, warning
except ImportError:
    def info(msg): print(f"[INFO] {msg}")
    def debug(msg): print(f"[DEBUG] {msg}")
    def error(msg): print(f"[ERROR] {msg}")
    def warning(msg): print(f"[WARN] {msg}")


class ProWaveDAQ:
    """ProWaveDAQ 振動數據採集類別"""

    # Modbus 寄存器定義
    REG_SAMPLE_RATE = 0x01       # 取樣率設定
    REG_FIFO_LEN = 0x02          # FIFO 長度
    REG_DATA_START = 0x03        # Raw data X 起始位址
    REG_CHIP_ID = 0x80           # 晶片 ID 起始位址

    CHANNEL_COUNT = 3            # X, Y, Z
    MAX_FIFO_SAMPLES = 41        # 一次最多 41 組 XYZ
    MAX_DATA_WORDS = MAX_FIFO_SAMPLES * CHANNEL_COUNT

    def __init__(self):
        """
        初始化 ProWaveDAQ 物件（只做狀態初始化，不連線）
        
        注意：此方法只初始化內部狀態變數，不建立 Modbus 連線。
        實際連線會在 init_devices() 方法中建立。
        """
        # ========== Modbus 連線相關參數 ==========
        self.client: Optional[ModbusSerialClient] = None  # Modbus RTU 客戶端物件
        self.serial_port = "/dev/ttyUSB0"  # 串列埠路徑（預設值，可透過 INI 檔案修改）
        self.baud_rate = 3000000  # 鮑率（預設 3Mbps，可透過 INI 檔案修改）
        self.sample_rate = 7812  # 取樣率（Hz，預設值，可透過 INI 檔案修改）
        self.slave_id = 1  # Modbus 從站 ID（預設值，可透過 INI 檔案修改）

        # ========== 讀取狀態變數 ==========
        self.counter = 0  # 成功讀取的批次計數器（用於統計）
        self.reading = False  # 讀取狀態旗標（True 表示正在讀取）
        self.reading_thread: Optional[threading.Thread] = None  # 讀取執行緒物件

        # ========== 資料佇列 ==========
        # 資料佇列：每次放「一批」浮點數，格式為 [X1, Y1, Z1, X2, Y2, Z2, ...]
        # 最大容量 1000 筆，超過時會丟棄最舊的資料
        self.data_queue: "queue.Queue[List[float]]" = queue.Queue(maxsize=1000)

        # ========== 相容舊版本欄位（避免外部引用錯誤） ==========
        # 以下欄位保留以維持向後相容性，但新版本不再使用
        self.latest_data: List[float] = []  # 最新資料快照（舊版 API）
        self.data_mutex = threading.Lock()  # 資料存取鎖（舊版 API）
        self.queue_mutex = threading.Lock()  # 佇列存取鎖（舊版 API）
        self.remaining_data: List[int] = []  # 剩餘資料緩衝區（舊版 API，現已不使用）
        self.remaining_data_lock = threading.Lock()  # 剩餘資料鎖（舊版 API）

    # ------------------------------------------------------------
    # 公開 API：裝置掃描 / 初始化
    # ------------------------------------------------------------
    def scan_devices(self) -> None:
        """
        掃描 /dev/ttyUSB* 下可用的 Modbus 設備
        
        此方法會掃描系統中所有符合 /dev/ttyUSB* 模式的串列埠設備，
        並在日誌中列出找到的設備。這有助於確認設備是否正確連接。
        
        注意：此方法只掃描設備，不會建立連線。
        """
        devices: List[str] = []
        # 使用正則表達式匹配 /dev/ttyUSB[0-9]+ 格式的設備名稱
        usb_pattern = re.compile(r'/dev/ttyUSB[0-9]+')

        try:
            # 掃描所有符合模式的設備
            for entry in glob.glob('/dev/ttyUSB*'):
                if usb_pattern.match(entry):
                    devices.append(entry)
        except Exception as e:
            error(f"Error scanning devices: {e}")
            return

        # 如果沒有找到設備，記錄錯誤並返回
        if not devices:
            error("No Modbus devices found!")
            return

        # 列出所有找到的設備
        debug("Available Modbus devices:")
        for i, dev in enumerate(devices, 1):
            debug(f"({i}) {dev}")

    def init_devices(self, filename: str) -> None:
        """
        從 INI 檔案初始化設備並建立 Modbus 連線
        INI 段落： [ProWaveDAQ]
            serialPort = /dev/ttyUSB0
            baudRate   = 3000000
            sampleRate = 7812
            slaveID    = 1
        """
        debug("Loading settings from INI file...")

        # 讀取 INI 參數
        try:
            config = configparser.ConfigParser()
            config.read(filename, encoding="utf-8")

            self.serial_port = config.get(
                "ProWaveDAQ", "serialPort", fallback="/dev/ttyUSB0"
            )
            self.baud_rate = config.getint(
                "ProWaveDAQ", "baudRate", fallback=3000000
            )
            self.sample_rate = config.getint(
                "ProWaveDAQ", "sampleRate", fallback=7812
            )
            self.slave_id = config.getint("ProWaveDAQ", "slaveID", fallback=1)

            debug(
                "Settings loaded from INI file:\n"
                f"  Serial Port: {self.serial_port}\n"
                f"  Baud Rate  : {self.baud_rate}\n"
                f"  Sample Rate: {self.sample_rate}\n"
                f"  Slave ID   : {self.slave_id}"
            )
        except Exception as e:
            error(f"Error parsing INI file: {e}")
            return

        # 建立連線
        if not self._connect():
            error("Failed to establish Modbus connection!")
            return

        # 讀取晶片 ID（非必要，但有助 debug）
        self._read_chip_id()

        # 設定取樣率
        self._set_sample_rate()

    # ------------------------------------------------------------
    # 公開 API：啟動 / 停止讀取
    # ------------------------------------------------------------
    def start_reading(self) -> None:
        """開始讀取振動數據（背景執行緒）"""
        if self.reading:
            warning("Reading is already in progress")
            return

        if not self._ensure_connected():
            error("Cannot start reading: Modbus connection not available")
            return

        # 清空狀態
        self.counter = 0
        with self.remaining_data_lock:
            self.remaining_data = []

        # 背景執行緒
        self.reading = True
        self.reading_thread = threading.Thread(
            target=self._read_loop, name="ProWaveDAQReadLoop"
        )
        self.reading_thread.daemon = True
        self.reading_thread.start()
        info("ProWaveDAQ reading started")

    def stop_reading(self) -> None:
        """停止讀取振動數據，並關閉連線"""
        if self.reading:
            self.reading = False
            if self.reading_thread and self.reading_thread.is_alive():
                self.reading_thread.join()

        self.counter = 0

        # 清空剩餘資料
        with self.remaining_data_lock:
            if self.remaining_data:
                warning(f"Discarding {len(self.remaining_data)} remaining raw data points on stop")
            self.remaining_data = []

        # 清空佇列
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except queue.Empty:
                break

        # 關閉連線
        self._disconnect()
        info("ProWaveDAQ reading stopped")

    # ------------------------------------------------------------
    # 公開 API：資料 / 狀態存取
    # ------------------------------------------------------------
    def get_data(self) -> List[float]:
        """
        非阻塞取得最新一批振動數據
        回傳：
            List[float]，格式為 [X1, Y1, Z1, X2, Y2, Z2, ...]
            若目前沒有資料則回傳空 list
        """
        try:
            return self.data_queue.get_nowait()
        except queue.Empty:
            return []

    def get_data_blocking(self, timeout: float = 0.1) -> List[float]:
        """
        阻塞取得最新一批振動數據
        timeout:
            最多等待秒數
        回傳：
            List[float]，格式為 [X1, Y1, Z1, ...]
            若 timeout 內無資料則回傳空 list
        """
        try:
            return self.data_queue.get(timeout=timeout)
        except queue.Empty:
            return []

    def get_counter(self) -> int:
        """回傳 read loop 成功處理的批次數"""
        return self.counter

    def reset_counter(self) -> None:
        """重置讀取批次計數器"""
        self.counter = 0

    def get_sample_rate(self) -> int:
        """回傳目前設定的取樣率"""
        return self.sample_rate

    # ------------------------------------------------------------
    # 內部：Modbus 連線維護
    # ------------------------------------------------------------
    def _connect(self) -> bool:
        """建立 Modbus RTU 連線"""
        try:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass

            self.client = ModbusSerialClient(
                port=self.serial_port,
                baudrate=self.baud_rate,
                timeout=1,
                parity="N",
                stopbits=1,
                bytesize=8,
                framer="rtu",
            )

            if not self.client.connect():
                error("ModbusSerialClient.connect() failed")
                self.client = None
                return False

            self.client.unit_id = self.slave_id
            info("Modbus connection established")
            return True
        except Exception as e:
            error(f"Error establishing Modbus connection: {e}")
            self.client = None
            return False

    def _disconnect(self) -> None:
        """關閉 Modbus 連線"""
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        finally:
            self.client = None

    def _ensure_connected(self) -> bool:
        """如果連線不存在或中斷，嘗試重連"""
        if not self.client:
            return self._connect()

        # pymodbus 3.x: 有 is_connected()
        try:
            if self.client.is_connected():
                return True
        except AttributeError:
            return True
        except Exception as e:
            warning(f"Error checking connection state: {e}")

        warning("Modbus connection lost, attempting to reconnect...")
        return self._connect()

    # ------------------------------------------------------------
    # 內部：初始化時讀取晶片 ID / 設定取樣率
    # ------------------------------------------------------------
    def _read_chip_id(self) -> None:
        """讀取晶片 ID（非關鍵功能，讀不到只記錄 log）"""
        if not self.client:
            return

        try:
            result = self.client.read_input_registers(
                address=self.REG_CHIP_ID, count=3
            )
            if result.isError():
                warning("Failed to read chip ID")
                return

            regs = result.registers
            if len(regs) >= 3:
                debug(f"Chip ID: {hex(regs[0])}, {hex(regs[1])}, {hex(regs[2])}")
            else:
                warning(f"Chip ID read length unexpected: {len(regs)}")
        except Exception as e:
            warning(f"Error reading chip ID: {e}")

    def _set_sample_rate(self) -> None:
        """寫入取樣率到寄存器"""
        if not self.client:
            return

        try:
            result = self.client.write_register(
                address=self.REG_SAMPLE_RATE, value=self.sample_rate
            )
            if result.isError():
                error("Failed to set sample rate")
            else:
                debug(f"Sample rate set to {self.sample_rate} Hz")
        except Exception as e:
            error(f"Error setting sample rate: {e}")

    # ------------------------------------------------------------
    # 內部：Modbus 讀取單次資料
    # ------------------------------------------------------------
    def _read_fifo_length(self) -> int:
        """
        讀取 FIFO 緩衝區長度（word 數）
        
        從 Modbus 寄存器 0x02 讀取 FIFO 中目前可用的資料長度。
        此長度表示目前 FIFO 中有多少個 16-bit word 的資料。
        
        Returns:
            int: FIFO 中的資料長度（word 數），如果讀取失敗則返回 0
        
        注意：
            - 此方法只讀取長度，不讀取實際資料
            - 如果連線不存在或讀取失敗，返回 0
        """
        if not self.client:
            return 0

        try:
            # 從寄存器 0x02 讀取 1 個 word（FIFO 長度）
            result = self.client.read_input_registers(
                address=self.REG_FIFO_LEN, count=1
            )
            if result.isError():
                warning("Failed to read FIFO length")
                return 0

            # 取得長度值並確保為非負數
            length = int(result.registers[0])
            return max(0, length)
        except Exception as e:
            warning(f"Error reading FIFO length: {e}")
            return 0

    def _read_raw_block(self, data_len: int) -> Optional[List[int]]:
        """
        讀取一批原始資料（純資料，不含 length 欄位）
        
        根據官方文件，Raw data (XYZ) 位於寄存器 0x03 ~ 0x7D。
        此方法從寄存器 0x03 開始讀取指定長度的原始資料。
        
        Args:
            data_len: 要讀取的資料長度（word 數），對應 FIFO 中目前的資料量
        
        Returns:
            Optional[List[int]]: 原始資料列表（16-bit 無符號整數），
                                如果讀取失敗則返回 None
        
        注意：
            - 讀取的資料長度會被限制在 MAX_DATA_WORDS 以內，避免意外過大
            - 如果實際讀取的長度小於請求的長度，返回 None（表示讀取不完整）
            - 返回的資料格式為：[X1, Y1, Z1, X2, Y2, Z2, ...]
        """
        if not self.client:
            return None

        # 限制最大讀取長度，避免意外過大（防止記憶體溢出）
        data_len = max(0, min(data_len, self.MAX_DATA_WORDS))
        if data_len <= 0:
            return None

        try:
            # 從寄存器 0x03 開始讀取「純 data」（不包含長度欄位）
            result = self.client.read_input_registers(
                address=self.REG_DATA_START,
                count=data_len,
            )
            if result.isError():
                warning("read_input_registers returned error")
                return None

            regs = result.registers
            # 檢查讀取的資料長度是否完整
            if len(regs) < data_len:
                warning(f"Read incomplete block: expected {data_len}, got {len(regs)}")
                return None

            return regs
        except Exception as e:
            warning(f"Error reading raw block: {e}")
            return None

    @staticmethod
    def _convert_raw_to_float_samples(raw_block: List[int]) -> List[float]:
        """
        將一批原始資料轉成浮點數列表，並保證 XYZ 通道不錯位
        
        此方法會：
        1. 只處理完整的 XYZ 三軸組（捨棄不足一組的資料）
        2. 將 16-bit 有符號整數轉換為浮點數（除以 8192.0）
        3. 確保輸出格式為 [X1, Y1, Z1, X2, Y2, Z2, ...]
        
        Args:
            raw_block: 原始資料列表（16-bit 無符號整數），格式為 [X, Y, Z, X, Y, Z, ...]
        
        Returns:
            List[float]: 轉換後的浮點數列表，格式為 [X1, Y1, Z1, X2, Y2, Z2, ...]
        
        注意：
            - 如果資料長度不是 3 的倍數，會自動捨棄最後不足一組 XYZ 的資料
            - 這是為了避免通道錯位（例如：如果最後只有 1 個值，無法確定是 X、Y 還是 Z）
            - 轉換公式：signed_value = (value < 32768) ? value : value - 65536
            - 最終浮點數 = signed_value / 8192.0
        """
        if not raw_block:
            return []

        # 只保留完整的 XYZ 三軸組（向下取整到最近的 3 的倍數）
        sample_word_count = (len(raw_block) // ProWaveDAQ.CHANNEL_COUNT) * ProWaveDAQ.CHANNEL_COUNT
        if sample_word_count <= 0:
            return []

        # 取出完整的資料（捨棄不足一組的部分）
        data_words = raw_block[:sample_word_count]

        # 將 16-bit 無符號整數轉換為有符號整數，再轉換為浮點數
        # 轉換規則：
        # - 如果值 < 32768，視為正數（0 ~ 32767）
        # - 如果值 >= 32768，視為負數（32768 ~ 65535 對應 -32768 ~ -1）
        # - 最終浮點數 = 有符號整數 / 8192.0
        float_samples: List[float] = []
        for w in data_words:
            # 轉換為有符號整數
            signed = w if w < 32768 else w - 65536
            # 轉換為浮點數（根據設備規格，需要除以 8192.0）
            float_samples.append(signed / 8192.0)

        return float_samples

    # ------------------------------------------------------------
    # 內部：read loop 主流程
    # ------------------------------------------------------------
    def _read_loop(self) -> None:
        """
        主要讀取迴圈（在背景執行緒中執行）
        
        此迴圈持續從 ProWaveDAQ 設備讀取振動資料，流程如下：
        1. 檢查 Modbus 連線狀態，如果斷線則嘗試重連
        2. 讀取 FIFO 長度（寄存器 0x02）
        3. 如果有資料，從寄存器 0x03 讀取原始資料
        4. 將原始資料轉換為浮點數（確保 XYZ 通道不錯位）
        5. 將轉換後的資料放入佇列，供外部取用
        
        重要設計原則：
        - 不跨批拼接 raw data，避免 X/Y/Z 通道錯位
        - 每次讀取只處理當次完整的 XYZ 三軸組
        - 如果佇列滿了，丟棄最舊的資料（FIFO 策略）
        
        錯誤處理：
        - 連續錯誤達到 max_consecutive_errors 次時，停止讀取迴圈
        - 連線失敗時會自動嘗試重連
        """
        consecutive_errors = 0  # 連續錯誤計數器
        max_consecutive_errors = 5  # 最大連續錯誤次數（超過此值則停止讀取）

        debug("Read loop started")

        while self.reading:
            # ========== 步驟 1：確保 Modbus 連線存在 ==========
            if not self._ensure_connected():
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    error("Too many connection failures, stopping read loop")
                    break
                # 連線失敗時等待 0.5 秒後重試
                time.sleep(0.5)
                continue

            try:
                # ========== 步驟 2：讀取 FIFO 長度 ==========
                fifo_len = self._read_fifo_length()
                if fifo_len <= 0:
                    # 沒有資料時短暫等待（0.1ms），避免 CPU 過載
                    time.sleep(0.0001)
                    continue

                # ========== 步驟 3：讀取原始資料 ==========
                raw_block = self._read_raw_block(fifo_len)
                if raw_block is None:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        error("Too many read failures, stopping read loop")
                        break
                    # 讀取失敗時等待 10ms 後重試
                    time.sleep(0.01)
                    continue

                # 讀取成功，重置錯誤計數器
                consecutive_errors = 0

                # ========== 步驟 4：轉換為浮點數（確保 XYZ 不錯位） ==========
                samples = self._convert_raw_to_float_samples(raw_block)
                if not samples:
                    # 理論上不會太常發生；若真的發生，多半是 length 與實際長度不一致
                    # 跳過此次讀取，繼續下一次
                    continue

                # ========== 步驟 5：將資料放入佇列 ==========
                # 如果佇列滿了，使用 FIFO 策略：丟棄最舊的資料，放入新資料
                try:
                    self.data_queue.put_nowait(samples)
                except queue.Full:
                    try:
                        # 佇列滿了，移除最舊的資料
                        self.data_queue.get_nowait()
                        # 放入新資料
                        self.data_queue.put_nowait(samples)
                    except queue.Empty:
                        # 如果移除失敗（理論上不應該發生），跳過此次
                        pass

                # 成功處理一批資料，增加計數器
                self.counter += 1

            except Exception as e:
                # 處理未預期的錯誤
                consecutive_errors += 1
                error(f"Error in read loop: {e}")
                if consecutive_errors >= max_consecutive_errors:
                    error("Too many consecutive errors, stopping read loop")
                    break
                # 發生錯誤時等待 100ms 後重試
                time.sleep(0.1)

        # 讀取迴圈結束，更新狀態
        self.reading = False
        debug("Read loop exited")

    # ------------------------------------------------------------
    # 解構子：確保離開前有停掉讀取與關閉連線
    # ------------------------------------------------------------
    def __del__(self):
        try:
            self.stop_reading()
        except Exception:
            pass