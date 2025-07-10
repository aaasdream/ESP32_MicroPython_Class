# main.py

# --- 模組導入 ---
import network
import time
import json
import asyncio
import gc  # 導入記憶體回收模組
from machine import Pin, ADC, time_pulse_us
from microdot import Microdot, send_file
from microdot.websocket import with_websocket

# --- WiFi 連線設定 ---
WIFI_SSID = 'HINET1'
WIFI_PASSWORD = '12345678'

# --- 硬體設定 ---
# 超音波感測器
TRIG_PIN_NUM = 27
ECHO_PIN_NUM = 13
# 可變電阻
POT_PIN_NUM = 39

# --- 初始化 GPIO 和 ADC ---
# 超音波
trigger = Pin(TRIG_PIN_NUM, Pin.OUT)
echo = Pin(ECHO_PIN_NUM, Pin.IN)
# 可變電阻 (ADC1_CH3)
potentiometer = ADC(Pin(POT_PIN_NUM))
# 設定衰減，讓 ADC 可以讀取 0-3.3V 的電壓
# ADC.ATTN_11DB 對應約 0-3.3V 的輸入範圍
potentiometer.atten(ADC.ATTN_11DB)

# --- 全域變數，用於儲存上一次有效的感測器數值 ---
last_valid_distance = -1.0
last_valid_pot_value = -1

# --- WiFi 連線函式 ---
def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print('正在連接到網路...')
        wlan.active(True)
        wlan.connect(ssid, password)
        # 等待連線成功
        while not wlan.isconnected():
            time.sleep(1)
            print('.')
    
    ip_address = wlan.ifconfig()[0]
    print(f'網路已連接！ IP 地址: {ip_address}')
    return ip_address

# --- 感測器讀取函式 ---
def get_distance():
    """觸發超音波感測器並回傳距離 (cm)"""
    trigger.value(0)
    time.sleep_us(2)
    trigger.value(1)
    time.sleep_us(10)
    trigger.value(0)
    
    try:
        # 設定 30000 微秒 (約 5 公尺) 的超時
        pulse_duration = time_pulse_us(echo, 1, 30000)
    except OSError:
        return -1.0

    if pulse_duration < 0:
        return -1.0
        
    distance_cm = (pulse_duration / 2) / 29.1
    return distance_cm

def get_pot_value():
    """讀取可變電阻的值 (0-4095)"""
    return potentiometer.read()

# --- Microdot App 和路由設定 ---
app = Microdot()

@app.route('/')
async def index(request):
    return send_file('web/index.html')

# 路由順序注意：WebSocket 路由需在靜態檔案路由之前
@app.route('/ws')
@with_websocket
async def ws_handler(request, ws):
    """WebSocket 處理器，持續傳送所有感測器數據"""
    global last_valid_distance, last_valid_pot_value
    print("WebSocket 客戶端已連接")
    
    while True:
        try:
            # 讀取超音波距離
            current_distance = get_distance()
            if current_distance >= 0:
                last_valid_distance = current_distance

            # 讀取可變電阻值
            last_valid_pot_value = get_pot_value()
            
            # 準備 JSON 數據，使用上一次的有效值
            payload = json.dumps({
                'distance': last_valid_distance,
                'potentiometer': last_valid_pot_value
            })

            # 透過 WebSocket 傳送數據
            await ws.send(payload)
            
            # 每秒傳送 10 次 (間隔 100ms)
            await asyncio.sleep_ms(100)

        except Exception as e:
            print(f"WebSocket 錯誤: {e}")
            break  # 當客戶端斷線或發生錯誤時，跳出迴圈
    
    print("WebSocket 客戶端已斷線")

@app.route('/<path:path>')
async def static(request, path):
    """靜態檔案伺服器"""
    if '..' in path:
        return "Path not allowed", 403
    full_path = 'web/' + path
    return send_file(full_path)

# --- 記憶體回收任務 ---
async def garbage_collector():
    """定期執行記憶體回收"""
    while True:
        gc.collect()
        gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
        # print(f"GC Ran. Free memory: {gc.mem_free()} bytes") # 可選：用於除錯
        await asyncio.sleep(30) # 每 30 秒執行一次

# --- 主執行程式 ---
async def main():
    try:
        connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        
        # 啟動記憶體回收任務
        asyncio.create_task(garbage_collector())
        
        print('啟動 Microdot 伺服器...')
        # 關閉除錯模式以獲得更好效能
        await app.start_server(port=80, debug=False)
        
    except KeyboardInterrupt:
        print("伺服器已停止")
    except Exception as e:
        print(f"發生嚴重錯誤: {e}")
        time.sleep(5)
        machine.reset()

# 使用 asyncio 執行主程式
asyncio.run(main())