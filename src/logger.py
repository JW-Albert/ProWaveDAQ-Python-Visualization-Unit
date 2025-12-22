#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
統一日誌系統模組

此模組提供統一的日誌輸出格式，所有日誌訊息都會自動包含時間戳記。
日誌格式：[YYYY-MM-DD HH:MM:SS] [LEVEL] 訊息內容

支援的日誌級別：
    - INFO: 一般資訊訊息（輸出到 stdout）
    - Debug: 調試訊息（輸出到 stdout，可關閉）
    - Error: 錯誤訊息（輸出到 stderr）
    - Warning: 警告訊息（輸出到 stdout）

使用方式：
    from logger import info, debug, error, warning
    
    info("這是一般資訊")
    debug("這是調試訊息")
    warning("這是警告訊息")
    error("這是錯誤訊息")
    
    # 關閉 Debug 訊息
    from logger import Logger
    Logger.set_debug_enabled(False)
"""

import sys
from datetime import datetime

class Logger:
    """統一日誌類別，提供統一的日誌輸出格式"""
    
    LEVEL_INFO = "INFO"
    LEVEL_DEBUG = "Debug"
    LEVEL_ERROR = "Error"
    LEVEL_WARNING = "Warning"
    _debug_enabled = True
    
    @classmethod
    def set_debug_enabled(cls, enabled: bool) -> None:
        """設定是否啟用 Debug 輸出"""
        cls._debug_enabled = enabled
    
    @classmethod
    def _format_message(cls, level: str, message: str) -> str:
        """格式化日誌訊息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] [{level}] {message}"
    
    @classmethod
    def info(cls, message: str) -> None:
        """輸出 INFO 級別日誌"""
        formatted = cls._format_message(cls.LEVEL_INFO, message)
        print(formatted, file=sys.stdout)
        sys.stdout.flush()
    
    @classmethod
    def debug(cls, message: str) -> None:
        """輸出 Debug 級別日誌"""
        if cls._debug_enabled:
            formatted = cls._format_message(cls.LEVEL_DEBUG, message)
            print(formatted, file=sys.stdout)
            sys.stdout.flush()
    
    @classmethod
    def error(cls, message: str) -> None:
        """輸出 Error 級別日誌"""
        formatted = cls._format_message(cls.LEVEL_ERROR, message)
        print(formatted, file=sys.stderr)
        sys.stderr.flush()
    
    @classmethod
    def warning(cls, message: str) -> None:
        """輸出 Warning 級別日誌"""
        formatted = cls._format_message(cls.LEVEL_WARNING, message)
        print(formatted, file=sys.stdout)
        sys.stdout.flush()


def info(message: str) -> None:
    """輸出 INFO 級別日誌"""
    Logger.info(message)

def debug(message: str) -> None:
    """輸出 Debug 級別日誌"""
    Logger.debug(message)

def error(message: str) -> None:
    """輸出 Error 級別日誌"""
    Logger.error(message)

def warning(message: str) -> None:
    """輸出 Warning 級別日誌"""
    Logger.warning(message)

