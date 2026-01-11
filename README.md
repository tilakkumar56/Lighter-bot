# Lighter.xyz Futures Trading Bot 🤖

A comprehensive Telegram bot for automated futures trading on [app.lighter.xyz](https://app.lighter.xyz) with support for paired/hedging strategies across multiple assets.

## Features ✨

- **Paired Trading**: Open two positions simultaneously (e.g., long BTC, short ETH)
- **Multi-Asset Support**: Trade BTC, ETH, and SOL futures
- **Automated Profit Booking**: Automatically closes positions when profit target is reached
- **Auto-Reopen Loop**: Reopens positions with the same setup after booking profit
- **Real-time Monitoring**: Continuously monitors positions and PnL
- **Emergency Controls**: Panic sell for quick position closure
- **Interactive Menu**: All commands available in Telegram menu

## Commands 📋

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and begin trade setup |
| `/trade` | Set up a new paired trade |
| `/status` | Check current positions and PnL |
| `/panic` | Emergency market sell all positions |
| `/stop` | Stop monitoring (keeps positions open) |
| `/help` | Show help message |

## Setup 🛠️

### Prerequisites

- Python 3.9+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Lighter.xyz API credentials

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd lighter-trading-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and fill in your credentials:
   ```env
   # Telegram Bot Configuration
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   
   # Lighter.xyz API Configuration
   LIGHTER_API_KEY=your_lighter_api_key_here
   LIGHTER_API_SECRET=your_lighter_api_secret_here
   LIGHTER_WALLET_ADDRESS=your_wallet_address_here
   
   # Optional: Custom API endpoint
   LIGHTER_API_URL=https://api.lighter.xyz
   
   # Allowed Telegram User IDs (comma-separated, for security)
   ALLOWED_USER_IDS=123456789
   
   # Monitoring interval in seconds (default: 5)
   MONITOR_INTERVAL=5
   ```

4. **Run the bot**
   ```bash
   python bot.py
   ```

### Getting Your Telegram User ID

To get your Telegram user ID for the `ALLOWED_USER_IDS` setting:
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID

### Getting Lighter.xyz API Credentials

1. Go to [app.lighter.xyz](https://app.lighter.xyz)
2. Connect your wallet
3. Navigate to API settings
4. Generate API key and secret
5. Copy your wallet address

## Usage 📖

### Setting Up a Paired Trade

1. Start the bot with `/start` or `/trade`
2. **Select Asset 1**: Choose BTC, ETH, or SOL
3. **Select Side 1**: Choose LONG or SHORT
4. **Enter Margin 1**: Amount in USD (e.g., 100)
5. **Enter Leverage 1**: 1-100 (e.g., 10)
6. **Select Asset 2**: Choose your second asset
7. **Select Side 2**: Choose LONG or SHORT
8. **Enter Margin 2**: Amount in USD
9. **Enter Leverage 2**: 1-100
10. **Enter Profit Target**: Target profit in USD (e.g., 50)
11. **Confirm**: Review and confirm your setup

### Example Trading Strategies

**Hedge Strategy:**
- Position 1: BTC LONG, $100 margin, 10x leverage
- Position 2: ETH SHORT, $100 margin, 10x leverage
- Profit Target: $50

**Spread Strategy:**
- Position 1: SOL LONG, $200 margin, 5x leverage
- Position 2: SOL SHORT, $200 margin, 5x leverage (different entry timing)
- Profit Target: $100

### Monitoring & Controls

- Use `/status` to check real-time PnL
- Use `/stop` to pause monitoring (positions stay open)
- Use `/panic` for emergency close of all positions

## Architecture 🏗️

```
├── bot.py              # Main Telegram bot with conversation handlers
├── lighter_client.py   # Lighter.xyz API client
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
└── README.md           # This file
```

## File Descriptions

### `bot.py`
- Main Telegram bot application
- Conversation handlers for trade setup flow
- Position monitoring and profit booking logic
- Command handlers (status, panic, stop)

### `lighter_client.py`
- API client for Lighter.xyz futures trading
- Position management (open, close, query)
- Price and PnL calculations
- Mock client for testing without API credentials

## Safety Features 🔒

- **User Authorization**: Restrict bot access to specific Telegram user IDs
- **Confirmation Step**: Review trade setup before execution
- **Panic Button**: Quick emergency close for all positions
- **Error Handling**: Graceful handling of API errors and disconnections

## Logging 📝

The bot logs important events including:
- Trade executions
- Position monitoring
- Profit booking
- Errors and warnings

## Development 🔧

### Running in Test Mode

If you don't provide API credentials, the bot uses a mock client for testing:
```python
# In lighter_client.py
class MockLighterClient(LighterClient):
    # Simulates trading without real API calls
```

### Extending the Bot

To add new assets:
```python
# In lighter_client.py
SUPPORTED_ASSETS = ['BTC', 'ETH', 'SOL', 'NEW_ASSET']
TRADING_PAIRS = {
    'BTC': 'BTC-USD',
    'ETH': 'ETH-USD',
    'SOL': 'SOL-USD',
    'NEW_ASSET': 'NEW_ASSET-USD'
}
```

## Disclaimer ⚠️

This bot is for educational purposes. Trading futures involves significant risk of loss. Always:
- Understand the risks involved
- Never trade more than you can afford to lose
- Test thoroughly before using real funds
- Monitor your positions regularly

## License 📄

MIT License - See LICENSE file for details

## Support 💬

For issues or feature requests, please open a GitHub issue.
