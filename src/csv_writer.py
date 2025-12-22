#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV 寫入器模組

此模組負責將振動數據寫入 CSV 檔案，支援：
- 自動分檔（根據資料量）
- 精確的時間戳記計算（根據取樣率，包含微秒精度）
- 高效能寫入（定期刷新機制，減少硬碟寫入次數）
- 檔案緩衝優化（128KB 緩衝區，減少系統呼叫）
- 批次寫入（使用 writerows 提升效能）
- 資料完整性保證（使用 os.fsync 確保寫入硬碟）
- 多通道資料寫入（預設 3 通道：X, Y, Z）
- 確保分檔時時間戳記連續（不會因為分檔而重置時間）
"""

import os
import csv
import time
from datetime import datetime, timedelta
from typing import List

try:
    from logger import info, debug, error, warning
except ImportError:
    def info(msg): print(f"[INFO] {msg}")
    def debug(msg): print(f"[Debug] {msg}")
    def error(msg): print(f"[Error] {msg}")
    def warning(msg): print(f"[Warning] {msg}")


class CSVWriter:
    def __init__(self, channels: int, output_dir: str, label: str, sample_rate: int = 7812):
        self.channels = channels
        self.output_dir = output_dir
        self.label = label
        self.sample_rate = sample_rate
        self.file_counter = 1
        self.current_file = None
        self.writer = None
        self.current_filename = None
        
        # 時間計算相關：使用全域計數器推算時間，避免 jitter
        self.global_start_time = datetime.now()
        self.global_sample_count = 0
        
        # --- 效能優化關鍵設定 ---
        self.last_flush_time = time.time()
        self.flush_interval = 1.0  # 每 1 秒才強制刷新一次硬碟
        
        self._create_output_directory()
        self._create_new_file()

    def _create_output_directory(self) -> None:
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            error(f"Error creating output directory: {e}")

    def _create_new_file(self) -> None:
        """建立新的 CSV 檔案"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{self.label}_{self.file_counter:03d}.csv"
        filepath = os.path.join(self.output_dir, filename)
        
        self.current_filename = f"{timestamp}_{self.label}_{self.file_counter:03d}"

        try:
            # 優化 1: 設定 buffering=131072 (128KB)，減少系統呼叫
            self.current_file = open(
                filepath, 'w', newline='', encoding='utf-8', buffering=131072
            )
            self.writer = csv.writer(self.current_file)

            # 寫入標題
            headers = ['Timestamp', 'Channel_1(X)', 'Channel_2(Y)', 'Channel_3(Z)']
            self.writer.writerow(headers)
            
            # 建立檔案時立即刷新一次，確保檔案確實建立
            self.current_file.flush()

            info(f"New CSV file created: {filename}")

        except Exception as e:
            error(f"Error creating CSV file: {e}")
    
    def get_current_filename(self) -> str:
        return self.current_filename if self.current_filename else ""

    def add_data_block(self, data: List[float]) -> None:
        """
        加入數據區塊並寫入 CSV
        """
        if not self.writer or not data:
            return

        try:
            sample_interval = 1.0 / self.sample_rate

            # 批次準備寫入資料
            rows = []
            for i in range(0, len(data), self.channels):
                # 使用計數器推算精確時間，避免累積誤差
                elapsed_time = self.global_sample_count * sample_interval
                timestamp = self.global_start_time + timedelta(seconds=elapsed_time)
                
                # 優化 2: 格式化時間字串 (包含微秒 %f)
                ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
                
                row = [ts_str]
                # 填入通道資料 (若不足則補 0)
                for j in range(self.channels):
                    if i + j < len(data):
                        row.append(data[i + j])
                    else:
                        row.append(0.0)
                rows.append(row)
                self.global_sample_count += 1

            # 一次寫入多行 (比 writerow 迴圈快)
            self.writer.writerows(rows)

            # 優化 3: 定期刷新 (Time-based Flush)
            # 不要每次都 flush，這會殺死效能
            current_time = time.time()
            if current_time - self.last_flush_time > self.flush_interval:
                self.current_file.flush()
                self.last_flush_time = current_time

        except Exception as e:
            error(f"Error writing CSV data: {e}")

    def update_filename(self) -> None:
        """切換檔案 (分檔功能)"""
        # 關閉舊檔前確保資料寫入
        if self.current_file:
            try:
                self.current_file.flush()
                os.fsync(self.current_file.fileno()) # 確保寫入物理硬碟
                self.current_file.close()
            except Exception as e:
                error(f"Error closing old file: {e}")

        self.file_counter += 1
        self._create_new_file()

    def close(self) -> None:
        """關閉寫入器"""
        if self.current_file:
            try:
                self.current_file.flush()
                os.fsync(self.current_file.fileno()) # 確保寫入物理硬碟
                self.current_file.close()
            except Exception as e:
                error(f"Error closing CSV file: {e}")
            
            self.current_file = None
            self.writer = None

    def __del__(self):
        self.close()
