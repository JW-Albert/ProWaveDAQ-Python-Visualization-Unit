#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV寫入器 - 用於將振動數據寫入CSV檔案
"""

import os
import csv
import time
from datetime import datetime
from typing import List


class CSVWriter:
    """CSV寫入器類別"""
    
    def __init__(self, channels: int, output_dir: str, label: str):
        """
        初始化CSV寫入器
        
        Args:
            channels: 通道數量
            output_dir: 輸出目錄
            label: 標籤名稱
        """
        self.channels = channels
        self.output_dir = output_dir
        self.label = label
        self.file_counter = 1
        self.current_file = None
        self.writer = None
        self._create_output_directory()
        self._create_new_file()
    
    def _create_output_directory(self) -> None:
        """建立輸出目錄"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            print(f"建立輸出目錄時發生錯誤: {e}")
    
    def _create_new_file(self) -> None:
        """建立新的CSV檔案"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{self.label}_{self.file_counter:03d}.csv"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            self.current_file = open(filepath, 'w', newline='', encoding='utf-8')
            self.writer = csv.writer(self.current_file)
            
            # 寫入標題行
            headers = ['Timestamp', 'Channel_1', 'Channel_2', 'Channel_3']
            self.writer.writerow(headers)
            self.current_file.flush()
            
            print(f"已建立新的CSV檔案: {filename}")
        
        except Exception as e:
            print(f"建立CSV檔案時發生錯誤: {e}")
    
    def add_data_block(self, data: List[float]) -> None:
        """
        新增數據區塊到CSV檔案
        
        Args:
            data: 振動數據列表
        """
        if not self.writer or not data:
            return
        
        try:
            timestamp = datetime.now().isoformat()
            
            # 將數據按通道分組
            for i in range(0, len(data), self.channels):
                row = [timestamp]
                for j in range(self.channels):
                    if i + j < len(data):
                        row.append(data[i + j])
                    else:
                        row.append(0.0)  # 如果數據不足，填充0
                
                self.writer.writerow(row)
            
            self.current_file.flush()
        
        except Exception as e:
            print(f"寫入CSV數據時發生錯誤: {e}")
    
    def update_filename(self) -> None:
        """更新檔案名稱（建立新檔案）"""
        if self.current_file:
            self.current_file.close()
        
        self.file_counter += 1
        self._create_new_file()
    
    def close(self) -> None:
        """關閉CSV檔案"""
        if self.current_file:
            self.current_file.close()
            self.current_file = None
            self.writer = None
    
    def __del__(self):
        """解構函數"""
        self.close()
