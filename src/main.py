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
from flask import Flask, render_template, request, jsonify, send_from_directory
from prowavedaq import ProWaveDAQ
from csv_writer import CSVWriter

# 設定工作目錄為專案根目錄（src 的上一層）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
os.chdir(PROJECT_ROOT)

# 將 src 資料夾添加到 Python 路徑，以便導入模組
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# 全域狀態變數（用於記憶體中資料傳遞）
app = Flask(__name__, template_folder='templates')
realtime_data: List[float] = []
data_lock = threading.Lock()
is_collecting = False
collection_thread: Optional[threading.Thread] = None
daq_instance: Optional[ProWaveDAQ] = None
csv_writer_instance: Optional[CSVWriter] = None
data_counter = 0
target_size = 0
current_data_size = 0
# 追蹤是否有活躍的前端連線（用於優化：無連線時不更新即時資料緩衝區）
last_data_request_time = 0
data_request_lock = threading.Lock()
DATA_REQUEST_TIMEOUT = 5.0  # 5 秒內沒有請求視為無活躍連線


def update_realtime_data(data: List[float]) -> None:
    """更新即時資料（供前端顯示）"""
    global realtime_data, data_counter, last_data_request_time
    
    # 檢查是否有活躍的前端連線
    with data_request_lock:
        has_active_connection = (time.time() - last_data_request_time) < DATA_REQUEST_TIMEOUT
    
    # 只有在有活躍連線時才更新即時資料緩衝區
    # 但始終更新計數器（用於狀態顯示）
    with data_lock:
        if has_active_connection:
            realtime_data.extend(data)
            # 限制記憶體使用，保留最近 10000 個資料點
            if len(realtime_data) > 10000:
                realtime_data = realtime_data[-10000:]
        data_counter += len(data)


def get_realtime_data() -> List[float]:
    """取得即時資料的副本"""
    with data_lock:
        return realtime_data.copy()


# Flask 路由
@app.route('/')
def index():
    """主頁：顯示設定表單、Label 輸入、開始/停止按鈕與折線圖"""
    return render_template('index.html')


@app.route('/files_page')
def files_page():
    """檔案瀏覽頁面"""
    return render_template('files.html')


@app.route('/data')
def get_data():
    """回傳目前最新資料 JSON 給前端"""
    global last_data_request_time
    # 更新最後請求時間（表示有活躍的前端連線）
    with data_request_lock:
        last_data_request_time = time.time()
    
    data = get_realtime_data()
    global data_counter
    return jsonify({
        'success': True,
        'data': data,
        'counter': data_counter
    })


@app.route('/status')
def get_status():
    """檢查資料收集狀態"""
    global is_collecting, data_counter
    return jsonify({
        'success': True,
        'is_collecting': is_collecting,
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
        # 重置請求時間追蹤
        with data_request_lock:
            global last_data_request_time
            last_data_request_time = 0

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

        # 建立輸出目錄（在專案根目錄的 output 資料夾中）
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        folder = f"{timestamp}_{label}"
        output_path = os.path.join(PROJECT_ROOT, "output", "ProWaveDAQ", folder)
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


@app.route('/files')
def list_files():
    """列出 output 目錄中的檔案和資料夾"""
    try:
        path = request.args.get('path', '')
        # 安全檢查：只允許在專案根目錄的 output/ProWaveDAQ 目錄下瀏覽
        base_path = os.path.join(PROJECT_ROOT, "output", "ProWaveDAQ")
        
        if path:
            # 確保路徑在 base_path 內
            full_path = os.path.join(base_path, path)
            # 標準化路徑以檢查是否在 base_path 內
            full_path = os.path.normpath(full_path)
            base_path_norm = os.path.normpath(os.path.abspath(base_path))
            full_path_abs = os.path.abspath(full_path)
            
            if not full_path_abs.startswith(base_path_norm):
                return jsonify({'success': False, 'message': '無效的路徑'})
        else:
            full_path = base_path
        
        if not os.path.exists(full_path):
            return jsonify({'success': False, 'message': '路徑不存在'})
        
        items = []
        try:
            for item in sorted(os.listdir(full_path)):
                item_path = os.path.join(full_path, item)
                relative_path = os.path.join(path, item) if path else item
                relative_path = relative_path.replace('\\', '/')  # 統一使用 /
                
                if os.path.isdir(item_path):
                    items.append({
                        'name': item,
                        'type': 'directory',
                        'path': relative_path
                    })
                else:
                    size = os.path.getsize(item_path)
                    items.append({
                        'name': item,
                        'type': 'file',
                        'path': relative_path,
                        'size': size
                    })
        except PermissionError:
            return jsonify({'success': False, 'message': '沒有權限讀取此目錄'})
        
        return jsonify({
            'success': True,
            'items': items,
            'current_path': path
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/download')
def download_file():
    """下載檔案"""
    try:
        path = request.args.get('path', '')
        if not path:
            return jsonify({'success': False, 'message': '請提供檔案路徑'})
        
        # 安全檢查：只允許下載專案根目錄的 output/ProWaveDAQ 目錄下的檔案
        base_path = os.path.join(PROJECT_ROOT, "output", "ProWaveDAQ")
        full_path = os.path.join(base_path, path)
        
        # 標準化路徑以檢查是否在 base_path 內
        full_path = os.path.normpath(full_path)
        base_path_norm = os.path.normpath(os.path.abspath(base_path))
        full_path_abs = os.path.abspath(full_path)
        
        if not full_path_abs.startswith(base_path_norm):
            return jsonify({'success': False, 'message': '無效的路徑'})
        
        if not os.path.exists(full_path):
            return jsonify({'success': False, 'message': '檔案不存在'})
        
        if os.path.isdir(full_path):
            return jsonify({'success': False, 'message': '無法下載資料夾'})
        
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


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