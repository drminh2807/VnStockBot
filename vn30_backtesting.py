import talib
from backtesting import Backtest, Strategy
from vnstock3 import Vnstock
import pandas as pd
import time
import os
import pickle
import subprocess

# Create a cache directory if it doesn't exist
cache_dir = 'cache'
os.makedirs(cache_dir, exist_ok=True)

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
                # print(f"BUY at {self.data.index[-1]}: Price: {self.data.Close[-1]}, Qty: {qty}")

        # Điều kiện bán: cả ba chỉ báo đều có tín hiệu bán
        elif (self.data.Close[-1] < self.ma10[-1] and   # Giá đóng cửa < MA-10
              self.stoch_k[-1] < self.stoch_d[-1] and   # Stochastic K < D
              self.macd[-1] < self.macdsignal[-1]) and self.position:     # MACD < Signal
            self.sell(size=self.position.size)
            # print(f"SELL at {self.data.index[-1]}: Price: {self.data.Close[-1]}, Qty: {self.position.size}, Profit: {self.position.pl:.0f} - {self.position.pl_pct*100:.2f}%")

def backtest(symbol, start_date, end_date):
    cache_file = os.path.join(cache_dir, f'{symbol}_{start_date}_{end_date}.pkl')
    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
    else:
        stock = Vnstock().stock(symbol=symbol, source='VCI')
        data_vnstock = stock.quote.history(start=start_date, end=end_date)
        data = data_vnstock.rename(str.capitalize, axis='columns')
        data.index = pd.to_datetime(data["Time"])
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)

    bt = Backtest(data, MyStrategy, cash=100_000_000, commission=0, trade_on_close=True)
    return bt.run()

def format_percentage(value):
    if isinstance(value, (int, float)):
        color = 'green' if value > 0 else 'red' if value < 0 else 'black'
        return f'<span style="color: {color}">{value:.2f}%</span>'
    return value

vn30 = Vnstock().stock(symbol='FPT', source='TCBS').listing.symbols_by_group('VN30')

comparison_data = []

for symbol in vn30:
    print(f"Processing symbol: {symbol}")
    
    stats_cache_file = os.path.join(cache_dir, f'stats_{symbol}.pkl')
    if os.path.exists(stats_cache_file):
        with open(stats_cache_file, 'rb') as f:
            five_year_stats, one_year_stats = pickle.load(f)
    else:
        five_year_stats = backtest(symbol, '2020-01-01', '2024-09-01')
        one_year_stats = backtest(symbol, '2023-09-01', '2024-09-01')
        with open(stats_cache_file, 'wb') as f:
            pickle.dump((five_year_stats, one_year_stats), f)

    # Append data for the current symbol to the list
    comparison_data.append({
        ('Symbol', ''): symbol,
        ('Return [%]', '5Y'): format_percentage(five_year_stats['Return [%]']),
        ('Return [%]', '1Y'): format_percentage(one_year_stats['Return [%]']),
        ('Buy & Hold Return [%]', '5Y'): format_percentage(five_year_stats['Buy & Hold Return [%]']),
        ('Buy & Hold Return [%]', '1Y'): format_percentage(one_year_stats['Buy & Hold Return [%]']),
        ('Max. Drawdown [%]', '5Y'): format_percentage(five_year_stats['Max. Drawdown [%]']),
        ('Max. Drawdown [%]', '1Y'): format_percentage(one_year_stats['Max. Drawdown [%]']),
        ('Max. Drawdown Duration', '5Y'): five_year_stats['Max. Drawdown Duration'],
        ('Max. Drawdown Duration', '1Y'): one_year_stats['Max. Drawdown Duration'],
        ('# Trades', '5Y'): five_year_stats['# Trades'],
        ('# Trades', '1Y'): one_year_stats['# Trades'],
        ('Win Rate [%]', '5Y'): format_percentage(five_year_stats['Win Rate [%]']),
        ('Win Rate [%]', '1Y'): format_percentage(one_year_stats['Win Rate [%]']),
        ('Best Trade [%]', '5Y'): format_percentage(five_year_stats['Best Trade [%]']),
        ('Best Trade [%]', '1Y'): format_percentage(one_year_stats['Best Trade [%]']),
        ('Worst Trade [%]', '5Y'): format_percentage(five_year_stats['Worst Trade [%]']),
        ('Worst Trade [%]', '1Y'): format_percentage(one_year_stats['Worst Trade [%]']),
        ('Avg. Trade [%]', '5Y'): format_percentage(five_year_stats['Avg. Trade [%]']),
        ('Avg. Trade [%]', '1Y'): format_percentage(one_year_stats['Avg. Trade [%]']),
        ('Max. Trade Duration', '5Y'): five_year_stats['Max. Trade Duration'],
        ('Max. Trade Duration', '1Y'): one_year_stats['Max. Trade Duration']
    })

    print(f"Completed processing for symbol: {symbol}")

# Create the DataFrame with multi-level columns
comparison_df = pd.DataFrame(comparison_data)
comparison_df.columns = pd.MultiIndex.from_tuples(comparison_df.columns)

# Generate HTML
html_content = comparison_df.to_html(classes='table table-striped table-hover', border=0, escape=False)

# Add Bootstrap CSS for better styling
html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .table {{
            font-size: 0.9em;
        }}
        th {{
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container-fluid">
        <h2 class="mt-4 mb-4">VN30 Backtesting Comparison</h2>
        {html_content}
    </div>
</body>
</html>
"""

# Write the HTML content to a file
output_file = 'comparison_results.html'
with open(output_file, 'w') as f:
    f.write(html_content)

# Get the absolute path of the file
absolute_path = os.path.abspath(output_file)

print(f"Results have been saved to: {absolute_path}")
print("Please open this file in your web browser to view the results.")

# Open the file automatically
subprocess.call(["open", absolute_path])
