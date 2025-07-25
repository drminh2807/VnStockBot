import datetime
import talib
from vnstock import Vnstock
import datetime
from mailjet_rest import Client
import os
from dotenv import load_dotenv
load_dotenv()

symbols = ["FPT", "CTR"]

def calculate_recommendation(data):
    ma10 = talib.MA(data.close, timeperiod=10)
    stoch_k, stoch_d = talib.STOCH(data.high, data.low, data.close, fastk_period=14, slowk_period=5, slowd_period=5)
    macd, macdsignal, _ = talib.MACD(data.close, fastperiod=8, slowperiod=17, signalperiod=9)

    if (data.close.iloc[-1] > ma10.iloc[-1] and stoch_k.iloc[-1] > stoch_d.iloc[-1] and macd.iloc[-1] > macdsignal.iloc[-1]):
        return "Mua"
    elif (data.close.iloc[-1] < ma10.iloc[-1] and stoch_k.iloc[-1] < stoch_d.iloc[-1] and macd.iloc[-1] < macdsignal.iloc[-1]):
        return "Bán"
    else:
        return "Trung lập"

def send_mail(subject, content):
    api_key = os.environ['MJ_APIKEY_PUBLIC']
    api_secret = os.environ['MJ_APIKEY_PRIVATE']
    mailjet = Client(auth=(api_key, api_secret), version='v3.1')
    data = {
    'Messages': [
            {
                "From": {
                    "Email": "minh@spritely.co",
                    "Name": "VnStockBot"
                },
                "To": [
                    {
                        "Email": "drminh2807@gmail.com",
                        "Name": "drminh2807@gmail.com"
                    }
                ],
                "TemplateID": 6244256,
                "TemplateLanguage": True,
                "Subject": subject,
                "Variables": {
                    "CONTENT": content
                }
            }
        ]
    }
    result = mailjet.send.create(data=data)
    return result.status_code

def generate_html_table():
    # Tạo danh sách để lưu kết quả
    rows = []

    for symbol in symbols:
        stock = Vnstock().stock(symbol=symbol, source='VCI')
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")

        stock_data = stock.quote.history(start='2024-01-01', end=yesterday_str)
        close_today = stock_data['close'].iloc[-1]
        close_yesterday = stock_data['close'].iloc[-2]

        # Tính toán chênh lệch phần trăm
        price_change_pct = ((close_today - close_yesterday) / close_yesterday) * 100

        # Tính toán khuyến nghị mua/bán
        recommendation = calculate_recommendation(stock_data)

        # Tạo hàng cho bảng
        rows.append(f"""
            <tr>
                <td>{symbol}</td>
                <td>{round(close_yesterday, 2)}</td>
                <td>{round(price_change_pct, 2)}%</td>
                <td>{recommendation}</td>
            </tr>
        """)

    # Tạo bảng HTML
    table_html = f"""
    <table border="1" cellpadding="5" cellspacing="0">
        <thead>
            <tr>
                <th>Mã</th>
                <th>Giá hôm qua</th>
                <th>Chênh lệch %</th>
                <th>Khuyến nghị</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """

    return table_html

html = generate_html_table()
send_mail("VnStockBot", html)