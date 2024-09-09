import pandas as pd
import yfinance as yf
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import talib

# Lấy dữ liệu mã FPT từ Yahoo Finance
data = yf.download('FPT.VN', start='2020-01-01', end='2024-09-01')

# Chiến lược dựa trên MACD
class MACDStrategy(Strategy):
    def init(self):
        # Tạo chỉ báo MACD
        macd, macdsignal, macdhist = talib.MACD(self.data.Close, fastperiod=12, slowperiod=26, signalperiod=9)
        self.macd = self.I(lambda: macd)
        self.signal = self.I(lambda: macdsignal)

    def next(self):
        # Điều kiện mua: MACD cắt lên đường signal và hiện không có vị thế
        if crossover(self.macd, self.signal) and self.position.size == 0:
            # Tính toán số tiền có thể mua với giá hiện tại và chia theo lô 100 cổ phiếu
            cash = self.equity  # Sử dụng self.broker.cash để lấy số tiền hiện tại
            price = self.data.Close[-1]
            size = cash // (100 * price) * 100  # Mua theo gói 100 cổ phiếu
            
            if size > 0:  # Nếu có đủ tiền để mua ít nhất 100 cổ phiếu
                self.buy(size=size)

        # Điều kiện bán: MACD cắt xuống đường signal và đang có vị thế mua
        elif crossover(self.signal, self.macd) and self.position.size > 0:
            self.sell()

# Khởi tạo Backtest
bt = Backtest(data, MACDStrategy, cash=100000000, commission=0)

# Chạy Backtest
stats = bt.run()

# Hiển thị kết quả
print(stats)

# Đồ thị kết quả
bt.plot()
