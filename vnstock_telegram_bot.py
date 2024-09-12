import telebot
from vnstock3 import Vnstock
import schedule
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
from bokeh.io import export_png

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
bot_state = {
    'channels': {}  # Each channel will have its own watchlist
}

# Load state from file
def load_state():
    global bot_state
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            bot_state['channels'] = {int(k): {'watchlist': set(v['watchlist'])} for k, v in data.get('channels', {}).items()}
        logger.info(f"State loaded: {len(bot_state['channels'])} channels")
    except FileNotFoundError:
        logger.info("No existing state found. Starting with empty state.")

# Save state to file
def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump({
            'channels': {str(k): {'watchlist': list(v['watchlist'])} for k, v in bot_state['channels'].items()}
        }, f)
    logger.info(f"State saved: {len(bot_state['channels'])} channels")

# Function to add a symbol to the watchlist
def add_symbol(channel_id, symbol):
    if channel_id not in bot_state['channels']:
        bot_state['channels'][channel_id] = {'watchlist': set()}
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
/add <symbol> - Add a stock symbol to your watchlist
/remove <symbol> - Remove a stock symbol from your watchlist
/list - List all symbols in your watchlist
/today - Get today's recommendations for your watchlist
/backtest <symbol> <duration> - Run a backtest for a symbol (e.g., /backtest VNM 1y)
/help - Show this help message
    """
    bot.reply_to(message, help_text)

# Command handler for /add
@bot.message_handler(commands=['add'])
def add_stock(message):
    try:
        _, symbol = message.text.split(maxsplit=1)
        symbol = symbol.upper()
        channel_id = message.chat.id
        if symbol not in get_watchlist(channel_id):
            add_symbol(channel_id, symbol)
            bot.reply_to(message, f"Added {symbol} to the watchlist.")
            logger.info(f"User {message.from_user.id} added {symbol} to watchlist in channel {channel_id}")
            
            # Get and send recommendation for the newly added symbol
            recommendation = get_recommendation(symbol)
            bot.send_message(channel_id, f"Current recommendation for {symbol}:\n{recommendation}")
            logger.info(f"Sent recommendation for {symbol} to channel {channel_id}")
        else:
            bot.reply_to(message, f"{symbol} is already in the watchlist.")
            logger.info(f"User {message.from_user.id} attempted to add existing symbol {symbol} in channel {channel_id}")
    except ValueError:
        bot.reply_to(message, "Please provide a symbol. Usage: /add <symbol>")
        logger.warning(f"User {message.from_user.id} failed to add symbol (invalid input)")

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

# Command handler for /today
@bot.message_handler(commands=['today'])
def send_today_recommendations(message):
    channel_id = message.chat.id
    watchlist = get_watchlist(channel_id)
    if watchlist:
        recommendations = [get_recommendation(symbol) for symbol in watchlist]
        message_text = "📊 Today's recommendations:\n" + "\n".join(recommendations)
        bot.reply_to(message, message_text)
        logger.info(f"Sent today's recommendations to channel {channel_id}")
    else:
        bot.reply_to(message, "The watchlist is empty. Use /add <symbol> to add stocks.")
        logger.info(f"User {message.from_user.id} requested recommendations but watchlist is empty in channel {channel_id}")

# Function to get stock recommendation
def get_recommendation(symbol):
    stock = Vnstock().stock(symbol=symbol, source='VCI')
    data = stock.quote.history(start=(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'), end=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
    
    if data.empty:
        return "No data available"

    last_price = data['close'].iloc[-1]
    last_change_percent = (data['close'].iloc[-1] - data['close'].iloc[-2]) / data['close'].iloc[-2] * 100

    # Use recommendation from vnstock_alert
    recommendation = calculate_recommendation(data)

    # Add emojis based on recommendation and change percentage
    if recommendation == "Buy":
        rec_emoji = "🟢"
    elif recommendation == "Sell":
        rec_emoji = "🔴"
    else:
        rec_emoji = "🟡"

    change_emoji = "🔺" if last_change_percent > 0 else "🔻" if last_change_percent < 0 else "➖"

    return f"{rec_emoji} {symbol}: {last_price:.2f} {change_emoji} ({last_change_percent:.2f}%) - {recommendation}"

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
        
        bot.reply_to(message, f"Running backtest for {symbol} over {duration}...")
        bt = run_backtest(symbol, duration)
        result = bt.run()
        bot.send_message(channel_id, str(result))
        send_backtest_plot(bt, symbol, channel_id)
        logger.info(f"Sent backtest results for {symbol} over {duration} to channel {channel_id}")
    except ValueError:
        bot.reply_to(message, "Please provide a symbol and duration. Usage: /backtest <symbol> <duration>")
        logger.warning(f"User {message.from_user.id} failed to run backtest (invalid input)")

def send_backtest_plot(bt, symbol, chat_id):
    # Create a plot of the stats
    fig = bt.plot(open_browser=False)
    
    # Save the plot as a PNG file
    png_file = f"{symbol}_backtest.png"
    export_png(fig, filename=png_file)

    
    # Send the PNG file to Telegram
    with open(png_file, 'rb') as photo:
        bot.send_photo(chat_id, photo)
    
    # Remove the temporary file
    os.remove(png_file)

def run_backtest(symbol, duration):
    # Convert duration to days
    duration_map = {'y': 365, 'm': 30, 'w': 7, 'd': 1}
    days = int(duration[:-1]) * duration_map[duration[-1].lower()]
    
    stock = Vnstock().stock(symbol=symbol, source='VCI')
    end_date = datetime.now() - timedelta(days=1)
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
    
    logger.info("Starting daily recommendations process")
    if now.weekday() < 5:
        for channel_id, channel_data in bot_state['channels'].items():
            watchlist = channel_data['watchlist']
            if watchlist:
                recommendations = [get_recommendation(symbol) for symbol in watchlist]
                message = "📊 Daily recommendations:\n" + "\n".join(recommendations)
                try:
                    bot.send_message(channel_id, message)
                    logger.info(f"Sent daily recommendations to channel {channel_id}")
                except telebot.apihelper.ApiException as e:
                    logger.error(f"Failed to send daily recommendations to channel {channel_id}: {e}")
    else:
        logger.info("Skipped daily recommendations (weekend)")

# Schedule the daily recommendations
schedule.every().day.at("08:00").do(send_daily_recommendations)

# Function to run scheduled tasks
def run_scheduled_tasks():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Start the bot
if __name__ == "__main__":
    logger.info("Starting the bot")
    load_state()  # Load the state when starting the bot
    import threading
    threading.Thread(target=run_scheduled_tasks, daemon=True).start()
    logger.info("Scheduled tasks thread started")
    bot.polling()
    logger.info("Bot stopped")
