import backtrader as bt
import yfinance as yf
import pandas as pd
# Định nghĩa chiến lược dựa trên Stochastic Oscillator
class StochasticOscillatorStrategy(bt.Strategy):
    params = (('k_period', 14), ('d_period', 3), ('overbought', 80), ('oversold', 20))
    
    def __init__(self):
        # Thêm chỉ báo Stochastic Oscillator
        self.stochastic = bt.indicators.Stochastic(self.data, period=self.params.k_period, period_dfast=self.params.d_period)
    
    def notify_trade(self, trade):
        print(f"price {trade.price} size {trade.size} pnl {trade.pnl}")
            
    def next(self):
        if not self.position:  # Nếu chưa có vị thế
            if self.stochastic.percK[0] < self.params.oversold and self.stochastic.percD[0] < self.params.oversold:
                self.buy()  # Mua khi cả %K và %D dưới mức oversold
        else:  # Nếu đang có vị thế
            if self.stochastic.percK[0] > self.params.overbought and self.stochastic.percD[0] > self.params.overbought:
                self.sell()  # Bán khi cả %K và %D trên mức overbought

# Tải dữ liệu từ Yahoo Finance cho FPT.VN
data = yf.download('FPT.VN', start='2020-01-01', end='2024-09-01')
data_bt = bt.feeds.PandasData(
    dataname=data,
    datetime=None,  # Chỉ định rằng cột index là cột datetime
    open='Open',
    high='High',
    low='Low',
    close='Close',
    volume='Volume',
)
# Khởi tạo Backtrader và thêm dữ liệu
cerebro = bt.Cerebro()
cerebro.adddata(data_bt)

# Thêm chiến lược vào hệ thống
cerebro.addstrategy(StochasticOscillatorStrategy)

# Đặt số tiền ban đầu
cerebro.broker.setcash(100000000)

# Đặt kích thước giao dịch cố định (lô cổ phiếu)
cerebro.addsizer(bt.sizers.FixedSize, stake=100)

# Chạy chiến lược
print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
cerebro.run()
print('Ending Portfolio Value: %.2f' % cerebro.broker.getvalue())

# Vẽ biểu đồ kết quả backtesting
cerebro.plot()
