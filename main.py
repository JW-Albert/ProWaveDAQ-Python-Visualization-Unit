#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProWaveDAQ 即時資料可視化系統 - 主控制程式
整合 DAQ、Web、CSV 三者運作
"""

import os
import sys
import time
import threading
import configparser
from datetime import datetime
from typing import List, Optional, Dict
from flask import Flask, render_template, request, jsonify
from prowavedaq import ProWaveDAQ
from csv_writer import CSVWriter

# 全域狀態變數（用於記憶體中資料傳遞）
app = Flask(__name__)
realtime_data: List[float] = []
data_lock = threading.Lock()
is_collecting = False
collection_thread: Optional[threading.Thread] = None
daq_instance: Optional[ProWaveDAQ] = None
csv_writer_instance: Optional[CSVWriter] = None
data_counter = 0
target_size = 0
current_data_size = 0


def update_realtime_data(data: List[float]) -> None:
    """更新即時資料（供前端顯示）"""
    global realtime_data, data_counter
    with data_lock:
        realtime_data.extend(data)
        data_counter += len(data)
        # 限制記憶體使用，保留最近 10000 個資料點
        if len(realtime_data) > 10000:
            realtime_data = realtime_data[-10000:]


def get_realtime_data() -> List[float]:
    """取得即時資料的副本"""
    with data_lock:
        return realtime_data.copy()


# Flask 路由
@app.route('/')
def index():
    """主頁：顯示設定表單、Label 輸入、開始/停止按鈕與折線圖"""
    return render_template('index.html')


@app.route('/data')
def get_data():
    """回傳目前最新資料 JSON 給前端"""
    data = get_realtime_data()
    global data_counter
    return jsonify({
        'success': True,
        'data': data,
        'counter': data_counter
    })


@app.route('/config', methods=['GET', 'POST'])
def config():
    """顯示與修改 ProWaveDAQ.ini、Master.ini"""
    ini_dir = "API"
    prodaq_ini = os.path.join(ini_dir, "ProWaveDAQ.ini")
    master_ini = os.path.join(ini_dir, "Master.ini")

    if request.method == 'POST':
        # 儲存設定檔
        try:
            prodaq_content = request.form.get('prodaq_content', '')
            master_content = request.form.get('master_content', '')

            # 寫入 ProWaveDAQ.ini
            with open(prodaq_ini, 'w', encoding='utf-8') as f:
                f.write(prodaq_content)

            # 寫入 Master.ini
            with open(master_ini, 'w', encoding='utf-8') as f:
                f.write(master_content)

            return jsonify({'success': True, 'message': '設定檔已儲存'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    # GET 請求：顯示設定檔編輯頁面
    try:
        with open(prodaq_ini, 'r', encoding='utf-8') as f:
            prodaq_content = f.read()
    except:
        prodaq_content = "[ProWaveDAQ]\nserialPort = /dev/ttyUSB0\nbaudRate = 3000000\nsampleRate = 7812\nslaveID = 1"

    try:
        with open(master_ini, 'r', encoding='utf-8') as f:
            master_content = f.read()
    except:
        master_content = "[SaveUnit]\nsecond = 5"

    return render_template('config.html',
                           prodaq_content=prodaq_content,
                           master_content=master_content)


@app.route('/start', methods=['POST'])
def start_collection():
    """啟動 DAQ、CSVWriter 與即時顯示"""
    global is_collecting, collection_thread, daq_instance, csv_writer_instance
    global target_size, current_data_size, realtime_data, data_counter

    if is_collecting:
        return jsonify({'success': False, 'message': '資料收集已在執行中'})

    try:
        data = request.get_json()
        label = data.get('label', '') if data else ''

        if not label:
            return jsonify({'success': False, 'message': '請提供資料標籤'})

        # 重置狀態
        with data_lock:
            realtime_data = []
            data_counter = 0
            current_data_size = 0

        # 載入設定檔
        ini_file_path = "API/Master.ini"
        config = configparser.ConfigParser()
        config.read(ini_file_path, encoding='utf-8')

        if not config.has_section('SaveUnit'):
            return jsonify({'success': False, 'message': '無法讀取 Master.ini'})

        save_unit = config.getint('SaveUnit', 'second', fallback=5)

        # 初始化 DAQ
        daq_instance = ProWaveDAQ()
        daq_instance.init_devices("API/ProWaveDAQ.ini")
        sample_rate = daq_instance.get_sample_rate()
        channels = 3  # 固定3通道

        # 計算目標大小
        expected_samples_per_second = sample_rate * channels
        target_size = save_unit * expected_samples_per_second

        # 建立輸出目錄
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        folder = f"{timestamp}_{label}"
        output_path = os.path.join("output", "ProWaveDAQ", folder)
        os.makedirs(output_path, exist_ok=True)

        # 初始化 CSV Writer
        csv_writer_instance = CSVWriter(channels, output_path, label)

        # 啟動資料收集執行緒
        is_collecting = True
        collection_thread = threading.Thread(
            target=collection_loop, daemon=True)
        collection_thread.start()

        daq_instance.start_reading()

        return jsonify({
            'success': True,
            'message': f'資料收集已啟動 (取樣率: {sample_rate} Hz, 分檔間隔: {save_unit} 秒)'
        })

    except Exception as e:
        is_collecting = False
        return jsonify({'success': False, 'message': f'啟動失敗: {str(e)}'})


@app.route('/stop', methods=['POST'])
def stop_collection():
    """停止所有執行緒、安全關閉"""
    global is_collecting, daq_instance, csv_writer_instance

    if not is_collecting:
        return jsonify({'success': False, 'message': '資料收集未在執行中'})

    try:
        is_collecting = False

        # 停止 DAQ
        if daq_instance:
            daq_instance.stop_reading()

        # 關閉 CSV Writer
        if csv_writer_instance:
            csv_writer_instance.close()

        return jsonify({'success': True, 'message': '資料收集已停止'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'停止失敗: {str(e)}'})


def collection_loop():
    """資料收集主迴圈（在獨立執行緒中執行）"""
    global is_collecting, daq_instance, csv_writer_instance
    global target_size, current_data_size

    while is_collecting:
        try:
            # 從 DAQ 取得資料（非阻塞）
            data = daq_instance.get_data()

            # 持續處理佇列中的所有資料（完全按照 main.py 的邏輯）
            while data and len(data) > 0:
                # 更新即時顯示
                update_realtime_data(data)

                # 寫入 CSV（完全按照 main.py 的邏輯）
                if csv_writer_instance:
                    current_data_size += len(data)

                    if current_data_size < target_size:
                        # 資料還未達到分檔門檻，直接寫入
                        csv_writer_instance.add_data_block(data)
                    else:
                        # 需要分檔處理
                        data_actual_size = len(data)  # 防止誤用 current_data_size
                        empty_space = target_size - \
                            (current_data_size - data_actual_size)

                        # 如果 current_data_size >= target_size，將資料分批處理
                        while current_data_size >= target_size:
                            batch = data[:empty_space]
                            csv_writer_instance.add_data_block(batch)

                            # 每個完整批次後更新檔案名稱
                            csv_writer_instance.update_filename()

                            current_data_size -= target_size

                        pending = data_actual_size - empty_space

                        # 處理剩餘資料（少於 target_size）
                        if pending:
                            remaining_data = data[empty_space:]
                            csv_writer_instance.add_data_block(remaining_data)
                            current_data_size = pending
                        else:
                            current_data_size = 0

                # 繼續從佇列取得下一筆資料
                data = daq_instance.get_data()

            # 短暫休息以避免 CPU 過載
            time.sleep(0.01)

        except Exception as e:
            print(f"[Error] Data collection loop error: {e}")
            time.sleep(0.1)


def run_flask_server():
    """在獨立執行緒中執行 Flask 伺服器"""
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)


def main():
    """主函數"""
    print("=" * 60)
    print("ProWaveDAQ Real-time Data Visualization System")
    print("=" * 60)
    print("Web interface will be available at http://0.0.0.0:8080/")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)

    # 在背景執行緒中啟動 Flask 伺服器
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()

    # 等待使用者中斷
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
        global is_collecting, daq_instance, csv_writer_instance
        if is_collecting:
            is_collecting = False
            if daq_instance:
                daq_instance.stop_reading()
            if csv_writer_instance:
                csv_writer_instance.close()
        print("Server has been shut down")


if __name__ == "__main__":
    main()

# In case I don't see you
# Good afternoon, Good evening, and good night.

# You got the dream
# You gotta protect it.