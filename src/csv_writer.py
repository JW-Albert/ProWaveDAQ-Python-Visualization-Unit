#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV 寫入器模組

負責將振動數據寫入 CSV 檔案，支援自動分檔、時間戳記計算和高效能寫入。
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
        
        self.global_start_time = datetime.now()
        self.global_sample_count = 0
        self.last_flush_time = time.time()
        self.flush_interval = 1.0
        
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
            self.current_file = open(
                filepath, 'w', newline='', encoding='utf-8', buffering=131072
            )
            self.writer = csv.writer(self.current_file)
            headers = ['Timestamp', 'Channel_1(X)', 'Channel_2(Y)', 'Channel_3(Z)']
            self.writer.writerow(headers)
            self.current_file.flush()
            info(f"New CSV file created: {filename}")
        except Exception as e:
            error(f"Error creating CSV file: {e}")
    
    def get_current_filename(self) -> str:
        return self.current_filename if self.current_filename else ""

    def add_data_block(self, data: List[float]) -> None:
        """加入數據區塊並寫入 CSV"""
        if not self.writer or not data:
            return

        try:
            sample_interval = 1.0 / self.sample_rate
            rows = []
            for i in range(0, len(data), self.channels):
                elapsed_time = self.global_sample_count * sample_interval
                timestamp = self.global_start_time + timedelta(seconds=elapsed_time)
                ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
                row = [ts_str]
                for j in range(self.channels):
                    if i + j < len(data):
                        row.append(data[i + j])
                    else:
                        row.append(0.0)
                rows.append(row)
                self.global_sample_count += 1

            self.writer.writerows(rows)

            current_time = time.time()
            if current_time - self.last_flush_time > self.flush_interval:
                self.current_file.flush()
                self.last_flush_time = current_time

        except Exception as e:
            error(f"Error writing CSV data: {e}")

    def update_filename(self) -> None:
        """切換檔案 (分檔功能)"""
        if self.current_file:
            try:
                self.current_file.flush()
                os.fsync(self.current_file.fileno())
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
                os.fsync(self.current_file.fileno())
                self.current_file.close()
            except Exception as e:
                error(f"Error closing CSV file: {e}")
            self.current_file = None
            self.writer = None

    def __del__(self):
        self.close()
