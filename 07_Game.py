# main.py (打磚塊遊戲版本)

# --- 模組導入 ---
import network
import time
import json
import asyncio
import gc
from machine import Pin, ADC, time_pulse_us
from neopixel import NeoPixel
from microdot import Microdot, send_file
from microdot.websocket import with_websocket

# --- WiFi 連線設定 ---
WIFI_SSID = 'HINET1'
WIFI_PASSWORD = '12345678'

# --- 硬體設定 ---
TRIG_PIN_NUM = 27
ECHO_PIN_NUM = 13
POT_PIN_NUM = 39
NEO_PIN_NUM = 2
NUM_LEDS = 2

# --- 初始化 GPIO、ADC 和 NeoPixel ---
trigger = Pin(TRIG_PIN_NUM, Pin.OUT)
echo = Pin(ECHO_PIN_NUM, Pin.IN)
potentiometer = ADC(Pin(POT_PIN_NUM))
potentiometer.atten(ADC.ATTN_11DB)
np = NeoPixel(Pin(NEO_PIN_NUM), NUM_LEDS)

# --- 全域變數 ---
last_valid_distance = -1.0
last_valid_pot_value = -1

# --- WiFi 連線函式 ---
def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print('正在連接到網路...')
        wlan.active(True)
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            time.sleep(1)
            print('.')
    ip_address = wlan.ifconfig()[0]
    print(f'網路已連接！ IP 地址: {ip_address}')
    return ip_address

# --- 感測器讀取函式 ---
def get_distance():
    trigger.value(0)
    time.sleep_us(2)
    trigger.value(1)
    time.sleep_us(10)
    trigger.value(0)
    try:
        pulse_duration = time_pulse_us(echo, 1, 30000)
    except OSError:
        return -1.0
    return (pulse_duration / 2) / 29.1 if pulse_duration > 0 else -1.0

def get_pot_value():
    return potentiometer.read()

# --- Microdot App 和路由設定 ---
app = Microdot()

@app.route('/')
async def index(request):
    return send_file('web/index.html')

@app.route('/ws')
@with_websocket
async def ws_handler(request, ws):
    global last_valid_distance, last_valid_pot_value
    print("WebSocket 客戶端已連接")

    async def sender():
        """定期將可變電阻和超音波數據傳送給網頁"""
        while True:
            current_distance = get_distance()
            if current_distance >= 0:
                last_valid_distance = current_distance
            
            last_valid_pot_value = get_pot_value()
            
            payload = json.dumps({
                'distance': last_valid_distance,
                'potentiometer': last_valid_pot_value
            })
            await ws.send(payload)
            await asyncio.sleep_ms(30) # 提高更新頻率以獲得流暢的遊戲控制

    async def receiver():
        """接收來自網頁的指令，主要是被擊中磚塊的顏色"""
        while True:
            msg = await ws.receive()
            try:
                data = json.loads(msg)
                if 'brick_color' in data:
                    color_hex = data['brick_color']
                    r = int(color_hex[1:3], 16)
                    g = int(color_hex[3:5], 16)
                    b = int(color_hex[5:7], 16)
                    
                    # 將兩顆 LED 設為相同顏色
                    np.fill((r, g, b))
                    np.write()
                    
            except (TypeError, ValueError, KeyError) as e:
                print(f"收到的 WebSocket 訊息無效: {msg}, 錯誤: {e}")

    sender_task = asyncio.create_task(sender())
    receiver_task = asyncio.create_task(receiver())
    try:
        await asyncio.gather(sender_task, receiver_task)
    except Exception as e:
        print(f"WebSocket 處理時發生錯誤: {e}")
    finally:
        sender_task.cancel()
        receiver_task.cancel()
        print("WebSocket 客戶端已斷線，任務已清理")

@app.route('/<path:path>')
async def static(request, path):
    if '..' in path: return "Path not allowed", 403
    return send_file('web/' + path)

async def garbage_collector():
    while True:
        gc.collect()
        await asyncio.sleep(30)

async def main():
    try:
        connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        
        # 初始硬體狀態
        np.fill((0, 0, 0))
        np.write()

        asyncio.create_task(garbage_collector())
        
        print('啟動 Microdot 伺服器...')
        await app.start_server(port=80, debug=False)
    except Exception as e:
        print(f"發生嚴重錯誤: {e}")
        time.sleep(5)
        machine.reset()

asyncio.run(main())