import requests
import ccxt
import pandas as pd
import ta
from datetime import datetime

TELEGRAM_TOKEN = "8711875284:AAGGERDv9njI0QZ9Fnrc1_tN9xeVLEXtnCc"  
TELEGRAM_CHAT_ID = "-1004394911035"

# ربط بورصة Binance
exchange = ccxt.binance()

def get_ohlcv(symbol, timeframe):
    """جلب بيانات الشموع اليابانية"""
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    return df

def find_pivots(series, left=5, right=5):
    """تحديد القمم والقيعان"""
    pivots = []
    for i in range(left, len(series) - right):
        is_high = all(series[i] >= series[i-j] for j in range(1, left+1)) and \
                  all(series[i] >= series[i+j] for j in range(1, right+1))
        is_low = all(series[i] <= series[i-j] for j in range(1, left+1)) and \
                  all(series[i] <= series[i+j] for j in range(1, right+1))
        if is_high:
            pivots.append((i, 'high', series[i]))
        elif is_low:
            pivots.append((i, 'low', series[i]))
    return pivots

def detect_hidden_divergence(df):
    """كشف الانعكاس المخفي"""
    signals = []
    price_pivots = find_pivots(df['close'])
    rsi_pivots = find_pivots(df['rsi'])
    
    # مطابقة آخر قمتين أو قاعين
    highs = [p for p in price_pivots if p[1] == 'high'][-2:]
    lows = [p for p in price_pivots if p[1] == 'low'][-2:]
    
    if len(highs) == 2:
        p1, p2 = highs
        r1 = df['rsi'].iloc[p1[0]]
        r2 = df['rsi'].iloc[p2[0]]
        # مخفي صاعد: سعر أعلى، RSI أدنى
        if p2[2] > p1[2] and r2 < r1:
            signals.append(('hidden_bullish', p1, p2, r1, r2))
    
    if len(lows) == 2:
        p1, p2 = lows
        r1 = df['rsi'].iloc[p1[0]]
        r2 = df['rsi'].iloc[p2[0]]
        # مخفي هابط: سعر أدنى، RSI أعلى
        if p2[2] < p1[2] and r2 > r1:
            signals.append(('hidden_bearish', p1, p2, r1, r2))
    
    return signals

def send_telegram(message):
    """إرسال رسالة للتيليجرام"""
    url = f"[api.telegram.org](https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage)"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    requests.post(url, json=payload)

def scan_market():
    """فحص جميع العملات"""
    tickers = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT']
    timeframes = ['15m', '1h']
    
    for symbol in tickers:
        for tf in timeframes:
            df = get_ohlcv(symbol, tf)
            signals = detect_hidden_divergence(df)
            for sig in signals:
                if sig[0] == 'hidden_bullish':
                    emoji = '🟢'
                    title = 'انعكاس مخفي صاعد'
                else:
                    emoji = '🔴'
                    title = 'انعكاس مخفي هابط'
                
                msg = f"""{emoji} *{title}*
━━━━━━━━━━━━━━━━━━━
العملة: `{symbol}`
الفريم: {tf}
السعر الحالي: ${df['close'].iloc[-1]:.2f}
الوقت: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC
━━━━━━━━━━━━━━━━━━━
📊 [TradingView](https://www.tradingview.com/chart/?symbol=BINANCE:{symbol.replace('/', '')})"""
                send_telegram(msg)

if __name__ == "__main__":
    scan_market()
