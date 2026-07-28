import os
import time
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

TELEGRAM_TOKEN = "8711875284:AAGGERDv9njI0QZ9Fnrc1_tN9xeVLEXtnCc"
CHAT_ID = "-1004394911035"

HOURS_OFFSET = 3

# قاموس لتسجيل التنبيهات المرسلة سابقاً لمنع التكرار نهائياً
sent_alerts = set()

def get_binance_futures_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        symbols = [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL' and s['status'] == 'TRADING']
        return symbols
    except Exception as e:
        print(f"Error fetching symbols: {e}")
    return []

def get_historical_klines(symbol, interval, limit=50):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if isinstance(data, list):
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['open'] = df['open'].astype(float)
            # ضبط توقيت الشمعة بدقة مع فارق الساعات المخصص
            df['candle_time'] = pd.to_datetime(df['timestamp'], unit='ms') + timedelta(hours=HOURS_OFFSET)
            return df
    except Exception as e:
        pass
    return None

def calculate_rsi_and_divergence(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    if len(df) < 30:
        return None, None
        
    lows = df['low'].values
    highs = df['high'].values
    rsis = df['rsi'].values
    
    curr_low = lows[-2]
    prev_low = lows[-15]
    curr_rsi = rsis[-2]
    prev_rsi = rsis[-15]
    
    hidden_bull = (curr_low > prev_low) and (curr_rsi < prev_rsi) and (rsis[-1] > rsis[-2])
    
    curr_high = highs[-2]
    prev_high = highs[-15]
    
    hidden_bear = (curr_high < prev_high) and (curr_rsi > prev_rsi) and (rsis[-1] < rsis[-2])
    
    return hidden_bull, hidden_bear

def send_telegram_alert(symbol, interval_str, div_type, price, candle_time):
    # إنشاء مفتاح فريد لا يتكرر أبداً لهذه الشمعة بالذات
    alert_key = f"{symbol}_{interval_str}_{candle_time}"
    
    if alert_key in sent_alerts:
        return  # تم إرسال تنبيه لهذه الشمعة مسبقاً، تجاهل تام لمنع التكرار
    
    sent_alerts.add(alert_key)
    
    # تنظيف الذاكرة للحفاظ على خفة السيرفر إذا كثرت المفاتيح
    if len(sent_alerts) > 3000:
        sent_alerts.clear()

    formatted_time = candle_time.strftime('%Y-%m-%d %H:%M:%S')

    text = f"""🚨 تنبيه دايفرجنس جديد

🪙 العملة: {symbol}#
⏱️ الفريم: {interval_str}
📊 نوع التنبيه: {div_type}
💵 السعر الحالي: {price:.4f}
⏰ الوقت: {formatted_time}"""

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload, timeout=3)
    except Exception as e:
        print(f"Telegram error: {e}")

def scan_market():
    symbols = get_binance_futures_symbols()
    intervals = {"15m": "15", "1h": "60"}
    
    for symbol in symbols:
        for binance_tf, label_tf in intervals.items():
            df = get_historical_klines(symbol, binance_tf, limit=40)
            if df is not None and not df.empty:
                h_bull, h_bear = calculate_rsi_and_divergence(df)
                
                current_price = df['close'].iloc[-2]
                candle_time = df['candle_time'].iloc[-2]
                
                # شرط الأمان الزمني: التأكد أن الشمعة التي يتم فحصها حديثة وليست قديمة لتجنب العشوائية
                now = datetime.now() + timedelta(hours=HOURS_OFFSET)
                time_diff = (now - candle_time).total_seconds() / 60
                
                # فريم 15 دقيقة يسمح بفارق بسيط، وفريم الساعة كذلك لضمان عدم تفويت الإغلاق وعدم إرسال قديم
                max_allowed_delay = 20 if label_tf == "15" else 65
                
                if time_diff <= max_allowed_delay:
                    if h_bull:
                        send_telegram_alert(symbol, label_tf, "Hidden Bullish Divergence", current_price, candle_time)
                    if h_bear:
                        send_telegram_alert(symbol, label_tf, "Hidden Bearish Divergence", current_price, candle_time)

@app.route("/")
def home():
    return "Bot is running with strict anti-duplicate and accurate timing!"

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=scan_market, trigger="interval", minutes=1)
    scheduler.start()
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
