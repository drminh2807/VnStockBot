import telebot
from vnstock3 import Vnstock
import time
from datetime import datetime, timedelta
import pytz
import os
from dotenv import load_dotenv
import talib
import json
import logging
from backtesting import Backtest, Strategy
import pandas as pd

# Load environment variables
load_dotenv()

# Initialize bot with your Telegram Bot API token from environment variable
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global variables
STATE_FILE = 'bot_state.json'
DEFAULT_RECOMMENDATION_TIME = "08:00"
bot_state = {
    'channels': {}  # Each channel will have its own watchlist and recommendation time
}

# Load state from file
def load_state():
    global bot_state
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            bot_state['channels'] = {
                int(k): {
                    'watchlist': set(v['watchlist']),
                    'recommendation_time': v.get('recommendation_time', DEFAULT_RECOMMENDATION_TIME)
                } for k, v in data.get('channels', {}).items()
            }
        logger.info(f"State loaded: {len(bot_state['channels'])} channels")
    except FileNotFoundError:
        logger.info("No existing state found. Starting with empty state.")

# Save state to file
def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump({
            'channels': {
                str(k): {
                    'watchlist': list(v['watchlist']),
                    'recommendation_time': v['recommendation_time']
                } for k, v in bot_state['channels'].items()
            }
        }, f)
    logger.info(f"State saved: {len(bot_state['channels'])} channels")

# Function to add a symbol to the watchlist
def add_symbol(channel_id, symbol):
    if channel_id not in bot_state['channels']:
        bot_state['channels'][channel_id] = {
            'watchlist': set(),
            'recommendation_time': DEFAULT_RECOMMENDATION_TIME
        }
    bot_state['channels'][channel_id]['watchlist'].add(symbol.upper())
    save_state()
    logger.info(f"Symbol {symbol.upper()} added to watchlist for channel {channel_id}")

# Function to remove a symbol from the watchlist
def remove_symbol(channel_id, symbol):
    if channel_id in bot_state['channels']:
        bot_state['channels'][channel_id]['watchlist'].discard(symbol.upper())
        save_state()
        logger.info(f"Symbol {symbol.upper()} removed from watchlist for channel {channel_id}")

# Function to get the watchlist
def get_watchlist(channel_id):
    return list(bot_state['channels'].get(channel_id, {}).get('watchlist', set()))

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

        # Điều kiện bán: cả ba chỉ báo đều có tín hiệu bán
        elif (self.data.Close[-1] < self.ma10[-1] and   # Giá đóng cửa < MA-10
              self.stoch_k[-1] < self.stoch_d[-1] and   # Stochastic K < D
              self.macd[-1] < self.macdsignal[-1]) and self.position:     # MACD < Signal
            self.sell(size=self.position.size)
# Command handler for /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Use /help to see available commands.")

# Command handler for /help
@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
📊 Available commands:
Note: The bot will automatically send recommendations for your watchlist every working day at 8:00 AM.

/add <symbol> - Add a stock symbol to your watchlist
/remove <symbol> - Remove a stock symbol from your watchlist
/list - List all symbols in your watchlist
/today - Get today's recommendations for your watchlist
/backtest <symbol> <duration> - Run a backtest for a symbol (e.g., /backtest VNM 1y)
/overview <symbol> - Get the overview of a symbol (e.g., /overview VNM)
/set_time <time> - Set the recommendation time for your watchlist (e.g., /set_time 09:00)
/help - Show this help message

Durations for backtest:
- y: years (e.g., 1y, 2y)
- m: months (e.g., 6m, 12m)
- w: weeks (e.g., 4w, 8w)
- d: days (e.g., 30d, 60d)
    """
    bot.reply_to(message, help_text)

# Command handler for /add
@bot.message_handler(commands=['add'])
def add_stock(message):
    try:
        _, *symbols = message.text.split()
        channel_id = message.chat.id
        added_symbols = []
        invalid_symbols = []
        existing_symbols = []

        for symbol in symbols:
            symbol = symbol.upper()
            if symbol not in get_watchlist(channel_id):
                try:
                    recommendation = get_recommendation(symbol)
                    if recommendation != "No data available":
                        add_symbol(channel_id, symbol)
                        added_symbols.append(symbol)
                        rec_type, rec_details = recommendation
                        bot.send_message(channel_id, f"Current recommendation for {symbol}:\n{rec_type}: {rec_details}")
                    else:
                        invalid_symbols.append(symbol)
                except Exception:
                    invalid_symbols.append(symbol)
            else:
                existing_symbols.append(symbol)

        response = []
        if added_symbols:
            response.append(f"Added to the watchlist: {', '.join(added_symbols)}")
        if invalid_symbols:
            response.append(f"Invalid symbols: {', '.join(invalid_symbols)}")
        if existing_symbols:
            response.append(f"Already in the watchlist: {', '.join(existing_symbols)}")

        bot.reply_to(message, "\n".join(response) if response else "No valid symbols provided.")
        logger.info(f"User {message.from_user.id} added symbols to watchlist in channel {channel_id}: added={added_symbols}, invalid={invalid_symbols}, existing={existing_symbols}")

    except ValueError:
        bot.reply_to(message, "Please provide at least one symbol. Usage: /add <symbol1> <symbol2> ...")
        logger.warning(f"User {message.from_user.id} failed to add symbols (invalid input)")

# Command handler for /remove
@bot.message_handler(commands=['remove'])
def remove_stock(message):
    try:
        _, symbol = message.text.split(maxsplit=1)
        symbol = symbol.upper()
        channel_id = message.chat.id
        if symbol in get_watchlist(channel_id):
            remove_symbol(channel_id, symbol)
            bot.reply_to(message, f"Removed {symbol} from the watchlist.")
            logger.info(f"User {message.from_user.id} removed {symbol} from watchlist in channel {channel_id}")
        else:
            bot.reply_to(message, f"{symbol} is not in the watchlist.")
            logger.info(f"User {message.from_user.id} attempted to remove non-existent symbol {symbol} in channel {channel_id}")
    except ValueError:
        bot.reply_to(message, "Please provide a symbol. Usage: /remove <symbol>")
        logger.warning(f"User {message.from_user.id} failed to remove symbol (invalid input)")

# Command handler for /list
@bot.message_handler(commands=['list'])
def list_stocks(message):
    channel_id = message.chat.id
    watchlist = get_watchlist(channel_id)
    if watchlist:
        bot.reply_to(message, "Current watchlist:\n" + "\n".join(watchlist))
    else:
        bot.reply_to(message, "The watchlist is empty.")

@bot.message_handler(commands=['overview'])
def overview_command(message):
    symbol = message.text.split()[1]
    overview = overview_command(symbol)
    bot.reply_to(message, overview)

# Command handler for /today
@bot.message_handler(commands=['today'])
def send_today_recommendations(message):
    channel_id = message.chat.id
    watchlist = get_watchlist(channel_id)
    if watchlist:
        message_text = format_recommendations_message(watchlist)
        
        bot.reply_to(message, message_text)
        logger.info(f"Sent today's recommendations to channel {channel_id}")
    else:
        bot.reply_to(message, "The watchlist is empty. Use /add <symbol> to add stocks.")
        logger.info(f"User {message.from_user.id} requested recommendations but watchlist is empty in channel {channel_id}")

@bot.message_handler(commands=['set_time'])
def set_recommendation_time(message):
    try:
        _, new_time = message.text.split(maxsplit=1)
        # Validate the time format
        valid_time = datetime.strptime(new_time, "%H:%M").strftime("%H:%M")
        channel_id = message.chat.id
        
        if channel_id not in bot_state['channels']:
            bot_state['channels'][channel_id] = {
                'watchlist': set(),
                'recommendation_time': DEFAULT_RECOMMENDATION_TIME
            }
        
        bot_state['channels'][channel_id]['recommendation_time'] = valid_time
        save_state()
        
        bot.reply_to(message, f"Daily recommendation time for this channel has been set to {valid_time}")
        logger.info(f"Daily recommendation time changed to {valid_time} for channel {channel_id}")
    except ValueError:
        bot.reply_to(message, "Invalid time format. Please use HH:MM format (e.g., 08:00)")
        logger.warning(f"User {message.from_user.id} failed to set recommendation time (invalid input)")


# Function to get stock recommendation
def get_recommendation(symbol):
    stock = Vnstock().stock(symbol=symbol, source='VCI')
    data = stock.quote.history(start=(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'), end=(datetime.now()).strftime('%Y-%m-%d'))
    
    if data.empty:
        return "No data available"

    last_price = data['close'].iloc[-1]
    last_change = data['close'].iloc[-1] - data['close'].iloc[-2]
    last_change_percent = last_change / data['close'].iloc[-2] * 100

    recommendation = calculate_recommendation(data)

    change_emoji = "🟩" if last_change_percent > 0 else "🟥" if last_change_percent < 0 else "🟨"
    change_emoji = "🟪" if last_change_percent >= 7 else change_emoji
    change_emoji = "🟦" if last_change_percent <= -7 else change_emoji

    return (recommendation, f"{symbol}: {last_price:.2f} {change_emoji} ({last_change:+.2f} {last_change_percent:+.2f}%)")

def calculate_indicators(data):
    ma10 = talib.MA(data.close, timeperiod=10)
    stoch_k, stoch_d = talib.STOCH(data.high, data.low, data.close, fastk_period=14, slowk_period=5, slowd_period=5)
    macd, macdsignal, _ = talib.MACD(data.close, fastperiod=8, slowperiod=17, signalperiod=9)
    return ma10, stoch_k, stoch_d, macd, macdsignal

def generate_signals(data, ma10, stoch_k, stoch_d, macd, macdsignal):
    buy_signal = (data.close > ma10) & (stoch_k > stoch_d) & (macd > macdsignal)
    sell_signal = (data.close < ma10) & (stoch_k < stoch_d) & (macd < macdsignal)
    return buy_signal, sell_signal

def calculate_recommendation(data):
    ma10, stoch_k, stoch_d, macd, macdsignal = calculate_indicators(data)
    buy_signal, sell_signal = generate_signals(data, ma10, stoch_k, stoch_d, macd, macdsignal)

    if buy_signal.iloc[-1]:
        return "Buy"
    elif sell_signal.iloc[-1]:
        return "Sell"
    else:
        return "Hold"

# Command handler for /backtest
@bot.message_handler(commands=['backtest'])
def backtest_stock(message):
    try:
        _, symbol, duration = message.text.split(maxsplit=2)
        symbol = symbol.upper()
        channel_id = message.chat.id
        
        bot.reply_to(message, f"Đang chạy backtest cho {symbol} trong khoảng thời gian {duration}...")
        bt = run_backtest(symbol, duration)
        result = bt.run()
        
        # Beautify the results
        beautified_results = beautify_backtest_results(result)
        bot.send_message(channel_id, beautified_results)

        logger.info(f"Đã gửi kết quả backtest cho {symbol} trong khoảng thời gian {duration} đến kênh {channel_id}")
    except ValueError:
        bot.reply_to(message, "Vui lòng cung cấp mã cổ phiếu và khoảng thời gian. Cách sử dụng: /backtest <mã cổ phi���u> <khoảng thời gian>")
        logger.warning(f"Người dùng {message.from_user.id} không thể chạy backtest (đầu vào không hợp lệ)")

def beautify_backtest_results(result):
    def format_duration(duration):
        return str(duration).split()[0] + ' ngày'

    # Extract relevant metrics and group them into sections
    sections = [
        ("📅 Thông tin backtest", [
            ('Vốn ban đầu', '100,000,000 đ'),
            ('Hoa hồng', '0 đ'),
            ('Bắt đầu', result['Start'].strftime('%Y-%m-%d')),
            ('Kết thúc', result['End'].strftime('%Y-%m-%d')),
            ('Thời gian', format_duration(result['Duration'])),
            ('Thời gian giao dịch', f"{result['Exposure Time [%]']:.2f}%"),
        ]),
        ("💰 Hiệu suất", [
            ('Vốn cuối cùng', f"{result['Equity Final [$]']:,.0f} đ"),
            ('Vốn cao nhất', f"{result['Equity Peak [$]']:,.0f} đ"),
            ('Lợi nhuận', f"{result['Return [%]']:.2f}%"),
            ('Lợi nhuận Mua & Giữ', f"{result['Buy & Hold Return [%]']:.2f}%"),
            ('Lợi nhuận hàng năm', f"{result['Return (Ann.) [%]']:.2f}%"),
            ('Biến động hàng năm', f"{result['Volatility (Ann.) [%]']:.2f}%"),
        ]),
        ("📊 Tỷ lệ", [
            ('Tỷ lệ Sharpe', f"{result['Sharpe Ratio']:.2f}"),
            ('Tỷ lệ Sortino', f"{result['Sortino Ratio']:.2f}"),
            ('Tỷ lệ Calmar', f"{result['Calmar Ratio']:.2f}"),
        ]),
        ("📉 Rủi ro", [
            ('Rủi ro tối đa', f"{result['Max. Drawdown [%]']:.2f}%"),
            ('Rủi ro trung bình', f"{result['Avg. Drawdown [%]']:.2f}%"),
            ('Thời gian rủi ro tối đa', format_duration(result['Max. Drawdown Duration'])),
            ('Thời gian rủi ro trung bình', format_duration(result['Avg. Drawdown Duration'])),
        ]),
        ("🔄 Giao dịch", [
            ('Số lượng giao dịch', result['# Trades']),
            ('Tỷ lệ thắng', f"{result['Win Rate [%]']:.2f}%"),
            ('Giao dịch tốt nhất', f"{result['Best Trade [%]']:.2f}%"),
            ('Giao dịch tệ nhất', f"{result['Worst Trade [%]']:.2f}%"),
            ('Giao dịch trung bình', f"{result['Avg. Trade [%]']:.2f}%"),
            ('Thời gian giao dịch tối đa', format_duration(result['Max. Trade Duration'])),
            ('Thời gian giao dịch trung bình', format_duration(result['Avg. Trade Duration'])),
        ]),
        ("📈 Chỉ số bổ sung", [
            ('Hệ số lợi nhuận', f"{result['Profit Factor']:.2f}"),
            ('Kỳ vọng', f"{result['Expectancy [%]']:.2f}%"),
            ('SQN', f"{result['SQN']:.2f}"),
            ('Tiêu chí Kelly', f"{result['Kelly Criterion']:.4f}"),
        ]),
    ]
    
    # Create a formatted string for the results
    return "\n\n".join([
        f"{section_name}\n" + "\n".join([f"{metric}:   {value}" for metric, value in section_metrics])
        for section_name, section_metrics in sections
    ])

def run_backtest(symbol, duration):
    # Convert duration to days
    duration_map = {'y': 365, 'm': 30, 'w': 7, 'd': 1}
    days = int(duration[:-1]) * duration_map[duration[-1].lower()]
    
    stock = Vnstock().stock(symbol=symbol, source='VCI')
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    data_vnstock = stock.quote.history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
    
    if data_vnstock.empty:
        return f"No data available for {symbol}"

    # Prepare data for backtesting
    data = data_vnstock.rename(str.capitalize, axis='columns')
    data.index = pd.to_datetime(data["Time"])

    return Backtest(data, MyStrategy, cash=100_000_000, commission=0)

# Function to send daily recommendations
def send_daily_recommendations():
    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(vietnam_tz)
    for channel_id, channel_data in bot_state['channels'].items():
        watchlist = channel_data['watchlist']
        recommendation_time = channel_data['recommendation_time']
        
        if now.strftime("%H:%M") == recommendation_time and watchlist:
            try:
                message = format_recommendations_message(watchlist)
                bot.send_message(channel_id, message)
                logger.info(f"Sent daily recommendations to channel {channel_id}")
            except telebot.apihelper.ApiException as e:
                bot.send_message(channel_id, f"Failed to send daily recommendations: {e}")
                logger.error(f"Failed to send daily recommendations to channel {channel_id}: {e}")

def overview_command(symbol):
    company = Vnstock().stock(symbol=symbol, source='TCBS').company
    overview_data = company.overview()

    # Define Vietnamese labels
    vietnamese_labels = {
        'exchange': 'Sàn',
        'industry': 'Ngành',
        'company_type': 'Loại công ty',
        'no_shareholders': 'Số cổ đông',
        'foreign_percent': 'Tỷ lệ sở hữu nước ngoài',
        'outstanding_share': 'Cổ phiếu lưu hành',
        'issue_share': 'Cổ phiếu phát hành',
        'established_year': 'Năm thành lập',
        'no_employees': 'Số nhân viên',
        'stock_rating': 'Xếp hạng cổ phiếu',
        'delta_in_week': 'Thay đổi trong tuần',
        'delta_in_month': 'Thay đổi trong tháng',
        'delta_in_year': 'Thay đổi trong năm',
        'short_name': 'Tên viết tắt',
        'website': 'Website',
        'industry_id': 'Mã ngành',
        'industry_id_v2': 'Mã ngành v2'
    }

    # Rename columns
    overview_data = overview_data.rename(columns=vietnamese_labels)

    # Convert all values to strings and format numeric values
    for col in overview_data.columns:
        if overview_data[col].dtype in ['float64', 'int64']:
            overview_data[col] = overview_data[col].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else "N/A")
        else:
            overview_data[col] = overview_data[col].astype(str).replace('nan', 'N/A')

    # Convert to dictionary for easier display
    overview_dict = overview_data.iloc[0].to_dict()

    # Print beautified output
    message = f"Tổng quan cổ phiếu {symbol}:\n"
    for key, value in overview_dict.items():
        message += f"{key}: {value}\n"
    return message

# Function to run scheduled tasks
def run_scheduled_tasks():
    while True:
        now = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
        if now.weekday() < 5:
            send_daily_recommendations()
        time.sleep(60)  # Sleep for 1 minute

# Add new function to get VNIndex info
def get_vnindex_info():
    try:
        vnindex = Vnstock().stock(symbol="VNINDEX", source='VCI')
        data = vnindex.quote.history(start=(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'), 
                                   end=datetime.now().strftime('%Y-%m-%d'))
        
        if data.empty:
            return "VNIndex: No data available"

        last_price = data['close'].iloc[-1]
        last_change = data['close'].iloc[-1] - data['close'].iloc[-2]
        last_change_percent = (last_change / data['close'].iloc[-2]) * 100

        change_emoji = "🟩" if last_change_percent > 0 else "🟥" if last_change_percent < 0 else "🟨"
        return f"VNIndex: {last_price:.2f} {change_emoji} ({last_change:+.2f} {last_change_percent:+.2f}%)"
    except Exception as e:
        logger.error(f"Error getting VNIndex data: {e}")
        return "VNIndex: Data unavailable"

# Add new function to get SJC gold price info
def get_sjc_gold_info():
    try:
        from vnstock3.explorer.misc.gold_price import sjc_gold_price
        gold_data = sjc_gold_price()
        
        # Get SJC 1L price (first row)
        sjc_price = gold_data.iloc[0]
        buy_price = sjc_price['buy_price']
        sell_price = sjc_price['sell_price']
        
        return f"Vàng SJC: 💰 Mua: {buy_price} | Bán: {sell_price}"
    except Exception as e:
        logger.error(f"Error getting SJC gold price data: {e}")
        return "Vàng SJC: Không có dữ liệu"

# Add new function to get BTC price info
def get_btc_info():
    try:
        crypto = Vnstock().crypto(symbol='BTC', source='MSN')
        data = crypto.quote.history(
            start=(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'),
            end=datetime.now().strftime('%Y-%m-%d')
        )
        
        if data.empty:
            return "BTC: No data available"

        last_price = data['close'].iloc[-1]
        last_change = data['close'].iloc[-1] - data['close'].iloc[-2]
        last_change_percent = (last_change / data['close'].iloc[-2]) * 100

        # Format price to show in millions
        price_in_millions = last_price / 1_000_000
        change_in_millions = last_change / 1_000_000

        change_emoji = "🟩" if last_change_percent > 0 else "🟥" if last_change_percent < 0 else "🟨"
        return f"Bitcoin: {price_in_millions:.2f}M {change_emoji} ({change_in_millions:+.2f}M {last_change_percent:+.2f}%)"
    except Exception as e:
        logger.error(f"Error getting BTC data: {e}")
        return "Bitcoin: Data unavailable"

def format_recommendations_message(watchlist):
    # Get VNIndex data first
    vnindex_info = get_vnindex_info()
    
    # Get SJC gold price
    gold_info = get_sjc_gold_info()
    
    # Get BTC price
    btc_info = get_btc_info()
    
    recommendations = [get_recommendation(symbol) for symbol in watchlist]
    
    # Sort recommendations
    buy_recs = [rec for rec in recommendations if rec[0] == "Buy"]
    sell_recs = [rec for rec in recommendations if rec[0] == "Sell"]
    hold_recs = [rec for rec in recommendations if rec[0] == "Hold"]
    
    # Create message with VNIndex, Gold price and BTC price
    message_text = f"📊 Today's recommendations:\n\n{vnindex_info}\n{gold_info}\n{btc_info}\n\n"
    if buy_recs:
        message_text += "🟢 BUY:\n" + "\n".join([rec[1] for rec in buy_recs]) + "\n\n"
    if sell_recs:
        message_text += "🔴 SELL:\n" + "\n".join([rec[1] for rec in sell_recs]) + "\n\n"
    if hold_recs:
        message_text += "🟡 HOLD:\n" + "\n".join([rec[1] for rec in hold_recs])
    return message_text

# Start the bot
if __name__ == "__main__":
    logger.info("Starting the bot")
    load_state()  # Load the state when starting the bot
    import threading
    threading.Thread(target=run_scheduled_tasks, daemon=True).start()
    logger.info("Scheduled tasks thread started")
    bot.polling()
    logger.info("Bot stopped")