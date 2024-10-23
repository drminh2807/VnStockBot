# VNStock Telegram Bot

This project is a Telegram bot that provides information about Vietnamese stocks using the VNStock library.

## Installation

### Prerequisites

- Python 3.7+
- pip (Python package installer)
- Homebrew (for macOS users)
- PM2 (Process Manager for Node.js)

### Steps

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/vnstock_telegram_bot.git
   cd vnstock_telegram_bot
   ```

2. Create a virtual environment:
   ```
   python3 -m venv venv
   ```

3. Activate the virtual environment:
   - On macOS and Linux:
     ```
     source venv/bin/activate
     ```
   - On Windows:
     ```
     venv\Scripts\activate
     ```

4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

5. Install ChromeDriver (for macOS users):
   ```
   brew install --cask chromedriver
   ```
   Note: For other operating systems, please download ChromeDriver from the official website and add it to your system PATH.

## Running the Bot

To run the VNStock Telegram Bot using PM2, follow these steps:

1. Make sure you have Node.js and PM2 installed globally:
   ```
   npm install -g pm2
   ```

2. Start the bot using PM2:
   ```
   pm2 start vnstock_telegram_bot.py --interpreter python3
   ```

3. To view the bot's logs:
   ```
   pm2 logs vnstock_telegram_bot
   ```

4. To stop the bot:
   ```
   pm2 stop vnstock_telegram_bot
   ```

5. To restart the bot:
   ```
   pm2 restart vnstock_telegram_bot
   ```

## Configuration

Make sure to set up your Telegram Bot token and other necessary configurations in a `.env` file or as environment variables before running the bot.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
