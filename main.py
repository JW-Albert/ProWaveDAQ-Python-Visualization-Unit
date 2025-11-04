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
from flask import Flask, render_template_string, request, jsonify
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
    html_template = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ProWaveDAQ 即時資料可視化系統</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .section {
            margin-bottom: 30px;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .section h2 {
            margin-top: 0;
            color: #555;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input[type="text"], textarea {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        textarea {
            min-height: 100px;
            font-family: monospace;
            font-size: 12px;
        }
        button {
            padding: 10px 20px;
            margin: 5px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        .btn-start {
            background-color: #4CAF50;
            color: white;
        }
        .btn-start:hover {
            background-color: #45a049;
        }
        .btn-stop {
            background-color: #f44336;
            color: white;
        }
        .btn-stop:hover {
            background-color: #da190b;
        }
        .btn-save {
            background-color: #2196F3;
            color: white;
        }
        .btn-save:hover {
            background-color: #0b7dda;
        }
        .btn:disabled {
            background-color: #cccccc;
            cursor: not-allowed;
        }
        .status {
            padding: 10px;
            margin: 10px 0;
            border-radius: 4px;
        }
        .status-success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status-error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .status-info {
            background-color: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        #chartContainer {
            position: relative;
            height: 500px;
            margin-top: 20px;
        }
        .info {
            background-color: #e7f3ff;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ProWaveDAQ 即時資料可視化系統</h1>
        
        <div id="statusArea"></div>
        
        <div class="section">
            <h2>設定與控制</h2>
            <div class="form-group">
                <label for="labelInput">資料標籤 (Label):</label>
                <input type="text" id="labelInput" placeholder="請輸入資料標籤">
            </div>
            <div class="form-group">
                <button class="btn btn-start" id="startBtn" onclick="startCollection()">開始讀取</button>
                <button class="btn btn-stop" id="stopBtn" onclick="stopCollection()" disabled>停止讀取</button>
            </div>
            <div class="info" id="infoArea">
                <strong>狀態：</strong><span id="statusText">待機中</span><br>
                <strong>資料點數：</strong><span id="dataCount">0</span>
            </div>
        </div>
        
        <div class="section">
            <h2>即時資料曲線</h2>
            <div id="chartContainer">
                <canvas id="realtimeChart"></canvas>
            </div>
        </div>
        
        <div class="section">
            <h2>設定檔管理</h2>
            <p><a href="/config">點擊這裡修改設定檔</a></p>
        </div>
    </div>
    
    <script>
        let chart = null;
        let dataUpdateInterval = null;
        let isCollecting = false;
        
        // 初始化 Chart.js
        function initChart() {
            const ctx = document.getElementById('realtimeChart').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: '通道 1',
                            data: [],
                            borderColor: 'rgb(255, 99, 132)',
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            tension: 0.1,
                            pointRadius: 0
                        },
                        {
                            label: '通道 2',
                            data: [],
                            borderColor: 'rgb(54, 162, 235)',
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            tension: 0.1,
                            pointRadius: 0
                        },
                        {
                            label: '通道 3',
                            data: [],
                            borderColor: 'rgb(75, 192, 192)',
                            backgroundColor: 'rgba(75, 192, 192, 0.1)',
                            tension: 0.1,
                            pointRadius: 0
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: false
                        },
                        x: {
                            display: false
                        }
                    },
                    plugins: {
                        legend: {
                            display: true
                        }
                    },
                    animation: {
                        duration: 0
                    }
                }
            });
        }
        
        // 更新圖表資料
        function updateChart() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.data && data.data.length > 0) {
                        // 將資料按通道分組（假設每3個資料點為一組：通道1、通道2、通道3）
                        const channel1 = [];
                        const channel2 = [];
                        const channel3 = [];
                        const labels = [];
                        
                        for (let i = 0; i < data.data.length; i += 3) {
                            if (i < data.data.length) channel1.push(data.data[i]);
                            if (i + 1 < data.data.length) channel2.push(data.data[i + 1]);
                            if (i + 2 < data.data.length) channel3.push(data.data[i + 2]);
                            labels.push(i / 3);
                        }
                        
                        // 更新圖表（不斷延伸，不重繪）
                        chart.data.labels = labels;
                        chart.data.datasets[0].data = channel1;
                        chart.data.datasets[1].data = channel2;
                        chart.data.datasets[2].data = channel3;
                        
                        // 限制資料點數量以保持效能（保留最近5000個點）
                        if (chart.data.labels.length > 5000) {
                            const keep = 5000;
                            chart.data.labels = chart.data.labels.slice(-keep);
                            chart.data.datasets[0].data = chart.data.datasets[0].data.slice(-keep);
                            chart.data.datasets[1].data = chart.data.datasets[1].data.slice(-keep);
                            chart.data.datasets[2].data = chart.data.datasets[2].data.slice(-keep);
                        }
                        
                        chart.update('none'); // 'none' 模式以提升效能
                        
                        // 更新資料點數顯示
                        document.getElementById('dataCount').textContent = data.counter || 0;
                    }
                })
                .catch(error => {
                    console.error('更新資料時發生錯誤:', error);
                });
        }
        
        // 開始收集資料
        function startCollection() {
            const label = document.getElementById('labelInput').value.trim();
            if (!label) {
                showStatus('請輸入資料標籤！', 'error');
                return;
            }
            
            fetch('/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ label: label })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    isCollecting = true;
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('stopBtn').disabled = false;
                    document.getElementById('labelInput').disabled = true;
                    document.getElementById('statusText').textContent = '採集中...';
                    showStatus('資料收集已開始', 'success');
                    
                    // 開始每 200ms 更新圖表
                    if (dataUpdateInterval) clearInterval(dataUpdateInterval);
                    dataUpdateInterval = setInterval(updateChart, 200);
                } else {
                    showStatus('啟動失敗: ' + (data.message || '未知錯誤'), 'error');
                }
            })
            .catch(error => {
                showStatus('啟動時發生錯誤: ' + error, 'error');
            });
        }
        
        // 停止收集資料
        function stopCollection() {
            fetch('/stop', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    isCollecting = false;
                    document.getElementById('startBtn').disabled = false;
                    document.getElementById('stopBtn').disabled = true;
                    document.getElementById('labelInput').disabled = false;
                    document.getElementById('statusText').textContent = '已停止';
                    showStatus('資料收集已停止', 'info');
                    
                    // 停止更新圖表
                    if (dataUpdateInterval) {
                        clearInterval(dataUpdateInterval);
                        dataUpdateInterval = null;
                    }
                } else {
                    showStatus('停止失敗: ' + (data.message || '未知錯誤'), 'error');
                }
            })
            .catch(error => {
                showStatus('停止時發生錯誤: ' + error, 'error');
            });
        }
        
        // 顯示狀態訊息
        function showStatus(message, type) {
            const statusArea = document.getElementById('statusArea');
            const statusClass = 'status-' + (type || 'info');
            statusArea.innerHTML = '<div class="status ' + statusClass + '">' + message + '</div>';
            setTimeout(() => {
                statusArea.innerHTML = '';
            }, 5000);
        }
        
        // 初始化
        window.onload = function() {
            initChart();
            // 初始更新一次
            updateChart();
        };
    </script>
</body>
</html>
    """
    return render_template_string(html_template)


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
    
    html_template = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>設定檔管理</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        textarea {
            width: 100%;
            min-height: 200px;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            box-sizing: border-box;
        }
        button {
            padding: 10px 20px;
            margin: 5px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            background-color: #2196F3;
            color: white;
        }
        button:hover {
            background-color: #0b7dda;
        }
        .status {
            padding: 10px;
            margin: 10px 0;
            border-radius: 4px;
        }
        .status-success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status-error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        a {
            color: #2196F3;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>設定檔管理</h1>
        <p><a href="/">← 返回主頁</a></p>
        <div id="statusArea"></div>
        
        <form id="configForm" onsubmit="saveConfig(event)">
            <div class="form-group">
                <label for="prodaq_content">ProWaveDAQ.ini:</label>
                <textarea id="prodaq_content" name="prodaq_content" required>{{ prodaq_content }}</textarea>
            </div>
            
            <div class="form-group">
                <label for="master_content">Master.ini:</label>
                <textarea id="master_content" name="master_content" required>{{ master_content }}</textarea>
            </div>
            
            <button type="submit">儲存設定檔</button>
        </form>
    </div>
    
    <script>
        function saveConfig(event) {
            event.preventDefault();
            
            const formData = new FormData(document.getElementById('configForm'));
            
            fetch('/config', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                const statusArea = document.getElementById('statusArea');
                if (data.success) {
                    statusArea.innerHTML = '<div class="status status-success">設定檔已成功儲存！</div>';
                } else {
                    statusArea.innerHTML = '<div class="status status-error">儲存失敗: ' + (data.message || '未知錯誤') + '</div>';
                }
            })
            .catch(error => {
                document.getElementById('statusArea').innerHTML = '<div class="status status-error">發生錯誤: ' + error + '</div>';
            });
        }
    </script>
</body>
</html>
    """
    return render_template_string(html_template, 
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
        collection_thread = threading.Thread(target=collection_loop, daemon=True)
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
                        empty_space = target_size - (current_data_size - data_actual_size)
                        
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
            print(f"[Error] 資料收集迴圈錯誤: {e}")
            time.sleep(0.1)


def run_flask_server():
    """在獨立執行緒中執行 Flask 伺服器"""
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)


def main():
    """主函數"""
    print("=" * 60)
    print("ProWaveDAQ 即時資料可視化系統")
    print("=" * 60)
    print("Web 介面將在 http://0.0.0.0:8080/ 啟動")
    print("按 Ctrl+C 停止伺服器")
    print("=" * 60)
    
    # 在背景執行緒中啟動 Flask 伺服器
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()
    
    # 等待使用者中斷
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在關閉伺服器...")
        global is_collecting, daq_instance, csv_writer_instance
        if is_collecting:
            is_collecting = False
            if daq_instance:
                daq_instance.stop_reading()
            if csv_writer_instance:
                csv_writer_instance.close()
        print("伺服器已關閉")


if __name__ == "__main__":
    main()

