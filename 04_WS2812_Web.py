# main.py

# --- 模組導入 ---
import network
import time
import json
import asyncio
import gc  # 導入記憶體回收模組
from machine import Pin, ADC, time_pulse_us
from neopixel import NeoPixel  # <--- 新增
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
# WS2812 LED
NEO_PIN_NUM = 2  # <--- 新增
NUM_LEDS = 2     # <--- 新增

# --- 初始化 GPIO、ADC 和 NeoPixel ---
# 超音波
trigger = Pin(TRIG_PIN_NUM, Pin.OUT)
echo = Pin(ECHO_PIN_NUM, Pin.IN)
# 可變電阻 (ADC1_CH3)
potentiometer = ADC(Pin(POT_PIN_NUM))
# 設定衰減，讓 ADC 可以讀取 0-3.3V 的電壓
# ADC.ATTN_11DB 對應約 0-3.3V 的輸入範圍
potentiometer.atten(ADC.ATTN_11DB)
# WS2812 LED
np = NeoPixel(Pin(NEO_PIN_NUM), NUM_LEDS) # <--- 新增

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
        pulse_duration = time_pulse_us(echo, 1, 30000)
    except OSError:
        return -1.0

    if pulse_duration < 0:
        return -1.0
        
    distance_cm = (pulse_duration / 2) / 29.1
    return distance_cm

def get_pot_value():
    """讀取可變電阻的值 (0-4095)"""
    # ESP32 的 ADC 是 12-bit，最大值為 4095
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
    """WebSocket 處理器，非同步處理感測器數據傳送和 LED 控制接收"""
    global last_valid_distance, last_valid_pot_value
    print("WebSocket 客戶端已連接")

    # --- 非同步任務：定期傳送感測器數據 ---
    async def sender():
        while True:
            # 讀取超音波距離
            current_distance = get_distance()
            if current_distance >= 0:
                last_valid_distance = current_distance

            # 讀取可變電阻值
            last_valid_pot_value = get_pot_value()
            
            # 準備 JSON 數據
            payload = json.dumps({
                'distance': last_valid_distance,
                'potentiometer': last_valid_pot_value
            })

            await ws.send(payload)
            await asyncio.sleep_ms(100) # 每秒傳送 10 次

    # --- 非同步任務：接收來自客戶端的指令 ---
    async def receiver():
        while True:
            msg = await ws.receive()
            try:
                data = json.loads(msg)
                if 'led' in data and 'color' in data:
                    led_index = data['led']
                    color_hex = data['color']
                    # 將 #RRGGBB 格式的顏色轉換為 (r, g, b) 元組
                    r = int(color_hex[1:3], 16)
                    g = int(color_hex[3:5], 16)
                    b = int(color_hex[5:7], 16)
                    
                    if 0 <= led_index < NUM_LEDS:
                        np[led_index] = (r, g, b)
                        np.write()
                        print(f"設定 LED {led_index} 顏色為 ({r}, {g}, {b})")

            except (TypeError, ValueError) as e:
                print(f"收到的 WebSocket 訊息無效: {msg}, 錯誤: {e}")

    # 建立並執行 sender 和 receiver 任務
    sender_task = asyncio.create_task(sender())
    receiver_task = asyncio.create_task(receiver())

    try:
        # 等待任一任務完成 (通常是因為客戶端斷線)
        await asyncio.gather(sender_task, receiver_task)
    except Exception as e:
        print(f"WebSocket 處理時發生錯誤: {e}")
    finally:
        # 清理任務
        sender_task.cancel()
        receiver_task.cancel()
        print("WebSocket 客戶端已斷線，任務已清理")


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
        await asyncio.sleep(30)

# --- 主執行程式 ---
async def main():
    try:
        connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        
        # 清空 LED 燈條
        np.fill((0, 0, 0))
        np.write()

        # 啟動記憶體回收任務
        asyncio.create_task(garbage_collector())
        
        print('啟動 Microdot 伺服器...')
        await app.start_server(port=80, debug=False)
        
    except KeyboardInterrupt:
        print("伺服器已停止")
    except Exception as e:
        print(f"發生嚴重錯誤: {e}")
        time.sleep(5)
        machine.reset()

# 使用 asyncio 執行主程式
asyncio.run(main())