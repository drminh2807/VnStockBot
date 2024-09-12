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
from functools import wraps

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
    'watchlist': set(),
    'channel_id': None
}

# Load state from file
def load_state():
    global bot_state
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            bot_state['watchlist'] = set(data.get('watchlist', []))
            bot_state['channel_id'] = data.get('channel_id')
        logger.info(f"State loaded: watchlist size {len(bot_state['watchlist'])}, channel ID {bot_state['channel_id']}")
    except FileNotFoundError:
        logger.info("No existing state found. Starting with empty state.")

# Save state to file
def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump({
            'watchlist': list(bot_state['watchlist']),
            'channel_id': bot_state['channel_id']
        }, f)
    logger.info(f"State saved: watchlist size {len(bot_state['watchlist'])}, channel ID {bot_state['channel_id']}")

# Function to add a symbol to the watchlist
def add_symbol(symbol):
    bot_state['watchlist'].add(symbol.upper())
    save_state()
    logger.info(f"Symbol added to watchlist: {symbol.upper()}")

# Function to remove a symbol from the watchlist
def remove_symbol(symbol):
    bot_state['watchlist'].discard(symbol.upper())
    save_state()
    logger.info(f"Symbol removed from watchlist: {symbol.upper()}")

# Function to get the watchlist
def get_watchlist():
    return list(bot_state['watchlist'])

def update_channel_id(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if 'channel_id' not in bot_state or bot_state['channel_id'] != message.chat.id:
            bot_state['channel_id'] = message.chat.id
            save_state()
            bot.reply_to(message, f"Channel ID updated to {bot_state['channel_id']}. You will receive updates here.")
            logger.info(f"Channel ID updated to {bot_state['channel_id']} for user {message.from_user.id}")
        return func(message, *args, **kwargs)
    return wrapper

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
/help - Show this help message
    """
    bot.reply_to(message, help_text)

# Command handler for /add
@bot.message_handler(commands=['add'])
@update_channel_id
def add_stock(message):
    try:
        _, symbol = message.text.split(maxsplit=1)
        symbol = symbol.upper()
        if symbol not in bot_state['watchlist']:
            add_symbol(symbol)
            bot.reply_to(message, f"Added {symbol} to the watchlist.")
            logger.info(f"User {message.from_user.id} added {symbol} to watchlist")
            send_watchlist_update_to_channel("added", symbol)
            
            # Get and send recommendation for the newly added symbol
            recommendation = get_recommendation(symbol)
            bot.send_message(message.chat.id, f"Current recommendation for {symbol}:\n{recommendation}")
            logger.info(f"Sent recommendation for {symbol} to user {message.from_user.id}")
        else:
            bot.reply_to(message, f"{symbol} is already in the watchlist.")
            logger.info(f"User {message.from_user.id} attempted to add existing symbol {symbol}")
    except ValueError:
        bot.reply_to(message, "Please provide a symbol. Usage: /add <symbol>")
        logger.warning(f"User {message.from_user.id} failed to add symbol (invalid input)")

# Command handler for /remove
@bot.message_handler(commands=['remove'])
@update_channel_id
def remove_stock(message):
    try:
        _, symbol = message.text.split(maxsplit=1)
        symbol = symbol.upper()
        if symbol in bot_state['watchlist']:
            remove_symbol(symbol)
            bot.reply_to(message, f"Removed {symbol} from the watchlist.")
            logger.info(f"User {message.from_user.id} removed {symbol} from watchlist")
            send_watchlist_update_to_channel("removed", symbol)
        else:
            bot.reply_to(message, f"{symbol} is not in the watchlist.")
            logger.info(f"User {message.from_user.id} attempted to remove non-existent symbol {symbol}")
    except ValueError:
        bot.reply_to(message, "Please provide a symbol. Usage: /remove <symbol>")
        logger.warning(f"User {message.from_user.id} failed to remove symbol (invalid input)")

# Command handler for /list
@bot.message_handler(commands=['list'])
@update_channel_id
def list_stocks(message):
    if bot_state['watchlist']:
        bot.reply_to(message, "Current watchlist:\n" + "\n".join(get_watchlist()))
    else:
        bot.reply_to(message, "The watchlist is empty.")

# Command handler for /today
@bot.message_handler(commands=['today'])
@update_channel_id
def send_today_recommendations(message):
    if bot_state['watchlist']:
        recommendations = [get_recommendation(symbol) for symbol in get_watchlist()]
        message_text = "📊 Today's recommendations:\n" + "\n".join(recommendations)
        bot.reply_to(message, message_text)
        logger.info(f"Sent today's recommendations to user {message.from_user.id}")
    else:
        bot.reply_to(message, "The watchlist is empty. Use /add <symbol> to add stocks.")
        logger.info(f"User {message.from_user.id} requested recommendations but watchlist is empty")

# Modify send_watchlist_update_to_channel function
def send_watchlist_update_to_channel(action, symbol):
    if bot_state['channel_id']:
        message = f"Watchlist {action}: {symbol}"
        try:
            bot.send_message(bot_state['channel_id'], message)
            logger.info(f"Sent watchlist update to channel: {message}")
        except telebot.apihelper.ApiException as e:
            logger.error(f"Failed to send message to channel: {e}")
    else:
        logger.warning("Attempted to send watchlist update, but channel ID is not set")

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

def calculate_recommendation(data):
    ma10 = talib.MA(data.close, timeperiod=10)
    stoch_k, stoch_d = talib.STOCH(data.high, data.low, data.close, fastk_period=14, slowk_period=5, slowd_period=5)
    macd, macdsignal, _ = talib.MACD(data.close, fastperiod=8, slowperiod=17, signalperiod=9)

    if (data.close.iloc[-1] > ma10.iloc[-1] and stoch_k.iloc[-1] > stoch_d.iloc[-1] and macd.iloc[-1] > macdsignal.iloc[-1]):
        return "Buy"
    elif (data.close.iloc[-1] < ma10.iloc[-1] and stoch_k.iloc[-1] < stoch_d.iloc[-1] and macd.iloc[-1] < macdsignal.iloc[-1]):
        return "Sell"
    else:
        return "Hold"

# Function to send daily recommendations
def send_daily_recommendations():
    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(vietnam_tz)
    
    logger.info("Starting daily recommendations process")
    if now.weekday() < 5 and bot_state['watchlist'] and bot_state['channel_id']:
        recommendations = [get_recommendation(symbol) for symbol in get_watchlist()]
        message = "📊 Daily recommendations:\n" + "\n".join(recommendations)
        try:
            bot.send_message(bot_state['channel_id'], message)
            logger.info(f"Sent daily recommendations to channel {bot_state['channel_id']}")
        except telebot.apihelper.ApiException as e:
            logger.error(f"Failed to send daily recommendations to channel: {e}")
    else:
        logger.info("Skipped daily recommendations (weekend, empty watchlist, or channel ID not set)")

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
