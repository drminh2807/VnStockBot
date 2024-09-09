import yfinance as yf
import talib
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import pandas as pd

# Tải dữ liệu từ Yahoo Finance
data = yf.download('FPT.VN', start='2020-09-01', end='2024-09-01')

# Chiến lược sử dụng chỉ báo Stochastic Oscillator
class StochasticStrategy(Strategy):
    oversold = 20  # Mức quá bán
    overbought = 80  # Mức quá mua
    take_profit = 0.15  # Chốt lãi 15%
    stop_loss = 0.07  # Cắt lỗ 7%
    def init(self):
        # Tính toán Stochastic Oscillator
        self.k, self.d = self.I(talib.STOCH, 
                                self.data.High, 
                                self.data.Low, 
                                self.data.Close,
                                fastk_period=14,  # Chu kỳ fastK
                                slowk_period=3,   # Chu kỳ slowK
                                slowk_matype=0,   # SMA
                                slowd_period=3,   # Chu kỳ slowD
                                slowd_matype=0)   # SMA
        
    def next(self):
        # Điều kiện mua: cả %K và %D dưới mức oversold và không có vị thế
        if self.k[-1] < self.oversold and self.d[-1] < self.oversold and not self.position:
            # Mua số cổ phiếu tối đa có thể chia hết cho 100
            size = self.equity // self.data.Close[-1] // 100 * 100
            if size > 0:
                self.buy(size=size)
                print(f'{self.data.index[-1]} - Giá: {self.data.Close[-1]:.2f} - Số lượng: {size} - Mua')
        
        if self.position:
            # Chốt lãi nếu lợi nhuận đạt 15%
            # if self.position.pl_pct >= self.take_profit:
            #     self.sell(size=self.position.size)
            #     print(f'{self.data.index[-1]} - Giá: {self.data.Close[-1]:.2f} - PnL: {self.position.pl:.0f} - BÁN (chốt lãi)')

            # # Cắt lỗ nếu lỗ vượt quá 7%
            # elif self.position.pl <= -self.stop_loss:
            #     self.sell(size=self.position.size)
            #     print(f'{self.data.index[-1]} - Giá: {self.data.Close[-1]:.2f} - PnL: {self.position.pl:.0f} - BÁN (cắt lỗ):')

            # Bán theo tín hiệu overbought
            if self.k[-1] > self.overbought and self.d[-1] > self.overbought:
                self.sell(size=self.position.size)
                # print(f'{self.data.index[-1]} - Giá: {self.data.Close[-1]:.2f} - PnL: {self.position.pl:.0f} - BÁN (quá mua): ')
                print(f'{self.data.index[-1]} - Giá: {self.data.Close[-1]:.2f} - PnL: {self.position.pl_pct*100:.2f} {self.position.pl:.0f} - Bán')

# Thực hiện backtest
bt = Backtest(
    data,
    StochasticStrategy,
    cash=100_000_000,  # 100 triệu tiền ban đầu
    commission=0,  # Không tính phí giao dịch
    trade_on_close=True  # Giao dịch tại giá đóng cửa của ngày
)

# Chạy backtest
result = bt.run()

# In kết quả tổng quan
print(result)

# Hiển thị biểu đồ kết quả
# bt.plot()
