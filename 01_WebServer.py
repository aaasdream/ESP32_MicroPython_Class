import network
import time
from microdot import Microdot, send_file

# --- WiFi 連線設定 ---
WIFI_SSID = 'HINET1'
WIFI_PASSWORD = '12345678'

# --- WiFi 連線函式 ---
def connect_wifi(ssid, password):
    """連接到 WiFi 網路"""
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print('正在連接到網路...')
        wlan.active(True)
        wlan.connect(ssid, password)
        # 等待連接成功
        while not wlan.isconnected():
            print(".", end="")
            time.sleep(1)
    
    ip_address = wlan.ifconfig()[0]
    print(f'\n網路已連接！ IP 地址: {ip_address}')
    return ip_address

# --- Microdot 網頁伺服器設定 ---
app = Microdot()

@app.route('/')
def index(request):
    """
    伺服器根目錄，自動提供 index.html
    """
    print("請求根目錄 /，回傳 index.html")
    return send_file('web/index.html')

@app.route('/<path:path>')
def static(request, path):
    """
    靜態檔案伺服器，用於提供 web 資料夾下的所有檔案
    例如：/style.css -> web/style.css
    """
    # 如果路徑結尾是 /，則預設提供 index.html
    if '/' in path:
        # 安全性檢查，防止目錄遍歷攻擊
        if '..' in path:
            return "Path not allowed", 403
    
    full_path = 'web/' + path
    print(f"請求靜態檔案: {full_path}")
    
    # send_file 會自動處理檔案不存在的情況 (回傳 404)
    return send_file(full_path)

# --- 主執行程式 ---
def main():
    try:
        # 1. 連接 WiFi
        connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        
        # 2. 啟動 Microdot 伺服器
        print('啟動 Microdot 伺服器...')
        # 使用 Port 80，這樣在瀏覽器中就不用輸入連接埠號
        app.run(port=80, debug=True)
        
    except KeyboardInterrupt:
        print("伺服器已停止")
    except Exception as e:
        print(f"發生錯誤: {e}")

# 執行主程式
main()