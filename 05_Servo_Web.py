# main.py

# --- 模組導入 ---
import network
import time
import json
import asyncio
import gc
from machine import Pin, ADC, time_pulse_us, PWM  # <--- 新增 PWM
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
SERVO_PIN_NUM = 23  # <--- 新增

# --- 初始化 GPIO、ADC、NeoPixel 和 PWM ---
# 超音波
trigger = Pin(TRIG_PIN_NUM, Pin.OUT)
echo = Pin(ECHO_PIN_NUM, Pin.IN)
# 可變電阻
potentiometer = ADC(Pin(POT_PIN_NUM))
potentiometer.atten(ADC.ATTN_11DB)
# WS2812 LED
np = NeoPixel(Pin(NEO_PIN_NUM), NUM_LEDS)
# 伺服馬達
servo = PWM(Pin(SERVO_PIN_NUM), freq=50) # <--- 新增，標準伺服馬達頻率為 50Hz

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

# --- 感測器與致動器函式 ---
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

def set_servo_from_normalized(value):
    """根據 0.0-1.0 的值設定伺服馬達角度 (0-180度)"""
    if not 0.0 <= value <= 1.0:
        return
    # 典型伺服馬達脈衝寬度: 0.5ms (0度) 到 2.5ms (180度)
    # 換算成奈秒: 500,000 ns 到 2,500,000 ns
    min_ns = 500000
    max_ns = 2500000
    duty_ns = int(min_ns + value * (max_ns - min_ns))
    servo.duty_ns(duty_ns)

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
            await asyncio.sleep_ms(100)

    async def receiver():
        while True:
            msg = await ws.receive()
            try:
                data = json.loads(msg)
                # 處理 LED 控制指令
                if 'led' in data and 'color' in data:
                    led_index = data['led']
                    color_hex = data['color']
                    r = int(color_hex[1:3], 16)
                    g = int(color_hex[3:5], 16)
                    b = int(color_hex[5:7], 16)
                    if 0 <= led_index < NUM_LEDS:
                        np[led_index] = (r, g, b)
                        np.write()
                        print(f"設定 LED {led_index} 顏色為 ({r}, {g}, {b})")
                # <--- 新增：處理伺服馬達控制指令 --->
                elif 'servo' in data:
                    servo_value = float(data['servo'])
                    set_servo_from_normalized(servo_value)
                    print(f"設定伺服馬達位置為: {servo_value * 100:.1f}%")

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
    if '..' in path:
        return "Path not allowed", 403
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
        set_servo_from_normalized(0.5) # 設定伺服馬達到中間位置 (90度)

        asyncio.create_task(garbage_collector())
        
        print('啟動 Microdot 伺服器...')
        await app.start_server(port=80, debug=False)
        
    except KeyboardInterrupt:
        print("伺服器已停止")
        servo.deinit() # <--- 新增：停止 PWM
    except Exception as e:
        print(f"發生嚴重錯誤: {e}")
        time.sleep(5)
        machine.reset()

asyncio.run(main())