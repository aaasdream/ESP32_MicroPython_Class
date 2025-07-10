import network
import time
import json
import asyncio
from machine import Pin, time_pulse_us
from microdot import Microdot, send_file
from microdot.websocket import with_websocket

# --- WiFi 連線設定 ---
WIFI_SSID = 'HINET1'
WIFI_PASSWORD = '12345678'

# --- 超音波感測器設定 ---
TRIG_PIN = 27
ECHO_PIN = 13

# 初始化 GPIO Pin
trigger = Pin(TRIG_PIN, Pin.OUT)
echo = Pin(ECHO_PIN, Pin.IN)

# 全域變數，用於儲存上一次有效的距離
last_distance = -1.0

# --- WiFi 連線函式 ---
def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print('正在連接到網路...')
        wlan.active(True)
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            time.sleep(1)
    
    ip_address = wlan.ifconfig()[0]
    print(f'網路已連接！ IP 地址: {ip_address}')
    return ip_address

# --- 超音波感測器讀取函式 ---
def get_distance():
    """觸發超音波感測器並回傳距離 (cm)"""
    # 觸發訊號
    trigger.value(0)
    time.sleep_us(2)
    trigger.value(1)
    time.sleep_us(10)
    trigger.value(0)
    
    # 測量回波時間，設定 30000 微秒 (約 5 公尺) 的超時
    try:
        pulse_duration = time_pulse_us(echo, 1, 30000)
    except OSError as e:
        # 如果超時，time_pulse_us 可能會拋出 OSError
        return -1.0

    # 如果 pulse_duration 小於 0，表示超時
    if pulse_duration < 0:
        return -1.0
        
    # 計算距離 (音速約 343 m/s 或 29.1 us/cm)
    # 距離 = (時間 * 音速) / 2 (因為是來回)
    distance_cm = (pulse_duration / 2) / 29.1
    return distance_cm

# --- Microdot App 和路由設定 ---
app = Microdot()

@app.route('/')
async def index(request):
    return send_file('web/index.html')

# !!! 注意：WebSocket 路由必須定義在靜態檔案路由之前 !!!
@app.route('/ws')
@with_websocket
async def ws_handler(request, ws):
    """WebSocket 處理器，持續傳送感測器數據"""
    global last_distance
    print("WebSocket 客戶端已連接")
    
    while True:
        try:
            # 讀取距離
            current_distance = get_distance()

            # 如果讀取成功，更新 last_distance
            # -1.0 代表讀取失敗 (例如超時)
            if current_distance >= 0:
                last_distance = current_distance
            
            # 準備 JSON 數據
            payload = json.dumps({
                'distance': last_distance
            })

            # 透過 WebSocket 傳送數據
            await ws.send(payload)
            
            # 每秒傳送 10 次 (間隔 100ms)
            await asyncio.sleep(0.1)

        except Exception as e:
            print(f"WebSocket 錯誤: {e}")
            break # 當客戶端斷線或發生錯誤時，跳出迴圈
    
    print("WebSocket 客戶端已斷線")

@app.route('/<path:path>')
async def static(request, path):
    """靜態檔案伺服器"""
    if '..' in path:
        return "Path not allowed", 403
    full_path = 'web/' + path
    return send_file(full_path)

# --- 主執行程式 ---
async def main():
    try:
        connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        
        print('啟動 Microdot 伺服器...')
        await app.start_server(port=80, debug=True)
        
    except KeyboardInterrupt:
        print("伺服器已停止")
    except Exception as e:
        print(f"發生錯誤: {e}")
        machine.reset()

# 使用 asyncio 執行主程式
asyncio.run(main())