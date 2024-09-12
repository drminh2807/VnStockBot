import talib
from backtesting import Backtest, Strategy
from vnstock3 import Vnstock
import pandas as pd
symbol = "NVL"

stock = Vnstock().stock(symbol=symbol, source='VCI')
data_vnstock = stock.quote.history(start='2020-01-01', end='2024-09-01')

# data.rename(columns={'open':'Open','high': 'High', 'low':'Low','close': 'Close','volume': "Volume"}, errors="raise")
data = data_vnstock.rename(str.capitalize, axis='columns')
data.index = pd.to_datetime(data["Time"])
# Chiến lược kết hợp Stochastic, MACD và MA
class MyStrategy(Strategy):
    def init(self):
        # MA-10
        self.ma10 = self.I(talib.MA, self.data.Close, timeperiod=10)
        
        # Stochastic 14-5
        self.stoch_k, self.stoch_d = self.I(talib.STOCH, self.data.High, self.data.Low, self.data.Close, 
                                            fastk_period=14, slowk_period=5, slowd_period=5)
        
        # MACD 8-17-9
        self.macd, self.macdsignal, _ = self.I(talib.MACD, self.data.Close, fastperiod=8, slowperiod=17, signalperiod=9)

    def next(self):
        # Điều kiện mua: cả ba chỉ báo đều có tín hiệu mua
        if (self.data.Close[-1] > self.ma10[-1] and    # Giá đóng cửa > MA-10
            self.stoch_k[-1] > self.stoch_d[-1] and    # Stochastic K > D
            self.macd[-1] > self.macdsignal[-1]) and not self.position:      # MACD > Signal
            # Tính số lượng cổ phiếu mua (làm tròn lô 100)
            qty = int(self.equity // self.data.Close[-1] // 100 * 100)
            if qty > 0:
                self.buy(size=qty)
                print(f"BUY at {self.data.index[-1]}: Price: {self.data.Close[-1]}, Qty: {qty}")

        # Điều kiện bán: cả ba chỉ báo đều có tín hiệu bán
        elif (self.data.Close[-1] < self.ma10[-1] and   # Giá đóng cửa < MA-10
              self.stoch_k[-1] < self.stoch_d[-1] and   # Stochastic K < D
              self.macd[-1] < self.macdsignal[-1]) and self.position:     # MACD < Signal
            self.sell(size=self.position.size)
            print(f"SELL at {self.data.index[-1]}: Price: {self.data.Close[-1]}, Qty: {self.position.size}, Profit: {self.position.pl:.0f} - {self.position.pl_pct*100:.2f}%")

# Cài đặt Backtest
bt = Backtest(data, MyStrategy, cash=100_000_000, commission=0, trade_on_close=True)

# Chạy backtest
stats = bt.run()

# In ra kết quả thống kê
print(stats)

bt.plot()