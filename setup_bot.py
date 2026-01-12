#!/usr/bin/env python3
"""
Run this script to create all bot files.
Usage: python setup_bot.py
"""

import os

FILES = {}

# ============== .env.example ==============
FILES['.env.example'] = '''# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Lighter.xyz API Configuration
LIGHTER_API_KEY=your_lighter_api_key_here
LIGHTER_API_SECRET=your_lighter_api_secret_here
LIGHTER_WALLET_ADDRESS=your_wallet_address_here

# Optional: Custom API endpoint (default: https://api.lighter.xyz)
LIGHTER_API_URL=https://api.lighter.xyz

# Allowed Telegram User IDs (comma-separated, for security)
ALLOWED_USER_IDS=your_telegram_user_id

# Monitoring interval in seconds (default: 5)
MONITOR_INTERVAL=5
'''

# ============== .gitignore ==============
FILES['.gitignore'] = '''.env
__pycache__/
*.py[cod]
*$py.class
venv/
.venv/
*.log
.DS_Store
'''

# ============== requirements.txt ==============
FILES['requirements.txt'] = '''python-telegram-bot==21.7
requests==2.32.3
aiohttp==3.11.11
python-dotenv==1.0.1
cryptography==43.0.3
'''

# ============== lighter_client.py ==============
FILES['lighter_client.py'] = '''"""
Lighter.xyz API Client for Futures Trading
"""
import os
import time
import hmac
import hashlib
import json
import logging
from typing import Optional, Dict, Any, List
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a trading position"""
    symbol: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    leverage: int
    margin: float
    unrealized_pnl: float
    realized_pnl: float
    liquidation_price: float
    position_id: Optional[str] = None
    
    @property
    def pnl_percentage(self) -> float:
        if self.margin == 0:
            return 0.0
        return (self.unrealized_pnl / self.margin) * 100


class LighterClient:
    """Client for interacting with Lighter.xyz futures trading API"""
    
    SUPPORTED_ASSETS = ['BTC', 'ETH', 'SOL']
    TRADING_PAIRS = {'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'SOL': 'SOL-USD'}
    
    def __init__(self, api_key: str, api_secret: str, wallet_address: str, base_url: str = "https://api.lighter.xyz"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.wallet_address = wallet_address
        self.base_url = base_url.rstrip('/')
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(self.api_secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
        return signature
    
    def _get_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, path, body)
        return {
            "Content-Type": "application/json",
            "X-API-KEY": self.api_key,
            "X-TIMESTAMP": timestamp,
            "X-SIGNATURE": signature,
            "X-WALLET-ADDRESS": self.wallet_address
        }
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        session = await self._get_session()
        path = f"/v1{endpoint}"
        url = f"{self.base_url}{path}"
        body = json.dumps(data) if data else ""
        headers = self._get_headers(method.upper(), path, body)
        
        try:
            async with session.request(method, url, headers=headers, data=body if body else None) as response:
                result = await response.json()
                if response.status >= 400:
                    error_msg = result.get('message', result.get('error', 'Unknown error'))
                    raise Exception(f"API Error: {error_msg}")
                return result
        except aiohttp.ClientError as e:
            raise Exception(f"Request failed: {e}")
    
    async def get_account_info(self) -> Dict[str, Any]:
        return await self._request("GET", "/account")
    
    async def get_balance(self) -> float:
        try:
            account = await self.get_account_info()
            return float(account.get('availableBalance', 0))
        except:
            return 0.0
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        pair = self.TRADING_PAIRS.get(symbol.upper(), f"{symbol.upper()}-USD")
        return await self._request("GET", f"/ticker/{pair}")
    
    async def get_mark_price(self, symbol: str) -> float:
        try:
            ticker = await self.get_ticker(symbol)
            return float(ticker.get('markPrice', ticker.get('lastPrice', 0)))
        except:
            return 0.0
    
    async def get_positions(self) -> List[Position]:
        try:
            result = await self._request("GET", "/positions")
            positions = []
            for pos_data in result.get('positions', []):
                pos = Position(
                    symbol=pos_data.get('symbol', '').replace('-USD', ''),
                    side=pos_data.get('side', 'long').lower(),
                    size=float(pos_data.get('size', 0)),
                    entry_price=float(pos_data.get('entryPrice', 0)),
                    mark_price=float(pos_data.get('markPrice', 0)),
                    leverage=int(pos_data.get('leverage', 1)),
                    margin=float(pos_data.get('margin', 0)),
                    unrealized_pnl=float(pos_data.get('unrealizedPnl', 0)),
                    realized_pnl=float(pos_data.get('realizedPnl', 0)),
                    liquidation_price=float(pos_data.get('liquidationPrice', 0)),
                    position_id=pos_data.get('positionId')
                )
                positions.append(pos)
            return positions
        except:
            return []
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol.upper() == symbol.upper():
                return pos
        return None
    
    async def open_position(self, symbol: str, side: str, margin: float, leverage: int) -> Dict[str, Any]:
        pair = self.TRADING_PAIRS.get(symbol.upper(), f"{symbol.upper()}-USD")
        mark_price = await self.get_mark_price(symbol)
        if mark_price <= 0:
            raise Exception(f"Could not get valid price for {symbol}")
        
        notional_value = margin * leverage
        size = notional_value / mark_price
        
        order_data = {
            "symbol": pair,
            "side": "buy" if side.lower() == "long" else "sell",
            "type": "market",
            "size": str(round(size, 8)),
            "leverage": str(leverage),
            "marginMode": "isolated",
            "reduceOnly": False
        }
        
        logger.info(f"Opening {side} position: {symbol} | Margin: ${margin} | Leverage: {leverage}x")
        return await self._request("POST", "/orders", order_data)
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        position = await self.get_position(symbol)
        if not position:
            raise Exception(f"No open position found for {symbol}")
        
        pair = self.TRADING_PAIRS.get(symbol.upper(), f"{symbol.upper()}-USD")
        close_side = "sell" if position.side == "long" else "buy"
        
        order_data = {
            "symbol": pair,
            "side": close_side,
            "type": "market",
            "size": str(position.size),
            "reduceOnly": True
        }
        
        logger.info(f"Closing position: {symbol} | Side: {position.side}")
        return await self._request("POST", "/orders", order_data)
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        positions = await self.get_positions()
        results = []
        for pos in positions:
            try:
                result = await self.close_position(pos.symbol)
                results.append({'symbol': pos.symbol, 'success': True, 'pnl': pos.unrealized_pnl, 'result': result})
            except Exception as e:
                results.append({'symbol': pos.symbol, 'success': False, 'error': str(e)})
        return results
    
    async def get_total_pnl(self) -> Dict[str, float]:
        positions = await self.get_positions()
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        total_realized = sum(p.realized_pnl for p in positions)
        total_margin = sum(p.margin for p in positions)
        return {
            'unrealized_pnl': total_unrealized,
            'realized_pnl': total_realized,
            'total_pnl': total_unrealized + total_realized,
            'total_margin': total_margin,
            'pnl_percentage': (total_unrealized / total_margin * 100) if total_margin > 0 else 0
        }


class MockLighterClient(LighterClient):
    """Mock client for testing without real API"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_positions: List[Position] = []
        self._mock_balance = 10000.0
        self._mock_prices = {'BTC': 45000.0, 'ETH': 2500.0, 'SOL': 100.0}
    
    async def get_balance(self) -> float:
        return self._mock_balance
    
    async def get_mark_price(self, symbol: str) -> float:
        import random
        base_price = self._mock_prices.get(symbol.upper(), 100.0)
        return base_price + base_price * random.uniform(-0.001, 0.001)
    
    async def get_positions(self) -> List[Position]:
        for pos in self._mock_positions:
            current_price = await self.get_mark_price(pos.symbol)
            pos.mark_price = current_price
            price_diff = current_price - pos.entry_price
            if pos.side == 'short':
                price_diff = -price_diff
            pos.unrealized_pnl = (price_diff / pos.entry_price) * pos.margin * pos.leverage
        return self._mock_positions
    
    async def open_position(self, symbol: str, side: str, margin: float, leverage: int) -> Dict[str, Any]:
        mark_price = await self.get_mark_price(symbol)
        size = (margin * leverage) / mark_price
        pos = Position(
            symbol=symbol.upper(), side=side.lower(), size=size,
            entry_price=mark_price, mark_price=mark_price, leverage=leverage,
            margin=margin, unrealized_pnl=0.0, realized_pnl=0.0,
            liquidation_price=mark_price * (0.5 if side == 'long' else 1.5),
            position_id=f"mock_{symbol}_{int(time.time())}"
        )
        self._mock_positions.append(pos)
        self._mock_balance -= margin
        return {'success': True, 'position': pos.position_id}
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        for i, pos in enumerate(self._mock_positions):
            if pos.symbol.upper() == symbol.upper():
                pnl = pos.unrealized_pnl
                self._mock_balance += pos.margin + pnl
                self._mock_positions.pop(i)
                return {'success': True, 'pnl': pnl}
        raise Exception(f"No position found for {symbol}")
'''

# ============== bot.py ==============
FILES['bot.py'] = '''"""
Lighter.xyz Futures Trading Telegram Bot
"""
import os
import asyncio
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

from lighter_client import LighterClient, MockLighterClient

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SELECT_ASSET_1, SELECT_SIDE_1, ENTER_MARGIN_1, ENTER_LEVERAGE_1 = range(4)
SELECT_ASSET_2, SELECT_SIDE_2, ENTER_MARGIN_2, ENTER_LEVERAGE_2 = range(4, 8)
ENTER_PROFIT_TARGET, CONFIRM_TRADE = range(8, 10)


@dataclass
class TradeSetup:
    asset_1: str = ""
    side_1: str = ""
    margin_1: float = 0.0
    leverage_1: int = 1
    asset_2: str = ""
    side_2: str = ""
    margin_2: float = 0.0
    leverage_2: int = 1
    profit_target: float = 0.0
    is_active: bool = False
    loop_enabled: bool = True


@dataclass
class UserSession:
    trade_setup: TradeSetup = field(default_factory=TradeSetup)
    monitoring_task: Optional[asyncio.Task] = None
    is_monitoring: bool = False
    total_profit_booked: float = 0.0
    trades_completed: int = 0


user_sessions: Dict[int, UserSession] = {}


def get_session(user_id: int) -> UserSession:
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()
    return user_sessions[user_id]


def get_lighter_client() -> LighterClient:
    api_key = os.getenv('LIGHTER_API_KEY', '')
    api_secret = os.getenv('LIGHTER_API_SECRET', '')
    wallet_address = os.getenv('LIGHTER_WALLET_ADDRESS', '')
    base_url = os.getenv('LIGHTER_API_URL', 'https://api.lighter.xyz')
    
    if not api_key or api_key == 'your_lighter_api_key_here':
        logger.warning("Using mock client - no API credentials provided")
        return MockLighterClient(api_key, api_secret, wallet_address, base_url)
    return LighterClient(api_key, api_secret, wallet_address, base_url)


def is_user_authorized(user_id: int) -> bool:
    allowed_ids = os.getenv('ALLOWED_USER_IDS', '')
    if not allowed_ids or allowed_ids == 'your_telegram_user_id':
        return True
    allowed_list = [int(uid.strip()) for uid in allowed_ids.split(',') if uid.strip()]
    return user_id in allowed_list


def get_asset_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("BTC", callback_data="asset_BTC"),
         InlineKeyboardButton("ETH", callback_data="asset_ETH"),
         InlineKeyboardButton("SOL", callback_data="asset_SOL")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_side_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("LONG", callback_data="side_long"),
         InlineKeyboardButton("SHORT", callback_data="side_short")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[
        InlineKeyboardButton("Confirm & Start", callback_data="confirm_yes"),
        InlineKeyboardButton("Cancel", callback_data="confirm_no")
    ]]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END
    
    get_session(user_id)
    welcome_text = """Lighter.xyz Futures Trading Bot

Commands:
/trade - Start new paired trade setup
/status - Check current PnL
/panic - Market sell all positions
/stop - Stop monitoring

Select Asset 1 to begin:"""
    await update.message.reply_text(welcome_text, reply_markup=get_asset_keyboard())
    return SELECT_ASSET_1


async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END
    
    session = get_session(user_id)
    if session.is_monitoring:
        await update.message.reply_text("A trade is already active. Use /stop first or /panic to close all.")
        return ConversationHandler.END
    
    session.trade_setup = TradeSetup()
    await update.message.reply_text("New Paired Trade Setup\\n\\nStep 1/9: Select Asset 1:", reply_markup=get_asset_keyboard())
    return SELECT_ASSET_1


async def select_asset_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Trade setup cancelled.")
        return ConversationHandler.END
    
    asset = query.data.replace("asset_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.asset_1 = asset
    
    await query.edit_message_text(f"Asset 1: {asset}\\n\\nStep 2/9: LONG or SHORT on {asset}?", reply_markup=get_side_keyboard())
    return SELECT_SIDE_1


async def select_side_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Trade setup cancelled.")
        return ConversationHandler.END
    
    side = query.data.replace("side_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.side_1 = side
    
    await query.edit_message_text(f"Asset 1: {session.trade_setup.asset_1} {side.upper()}\\n\\nStep 3/9: Enter margin amount in USD:")
    return ENTER_MARGIN_1


async def enter_margin_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        margin = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if margin <= 0:
            raise ValueError()
        session.trade_setup.margin_1 = margin
        
        await update.message.reply_text(f"Asset 1: {session.trade_setup.asset_1} {session.trade_setup.side_1.upper()}\\nMargin 1: ${margin:,.2f}\\n\\nStep 4/9: Enter leverage (1-100):")
        return ENTER_LEVERAGE_1
    except:
        await update.message.reply_text("Invalid amount. Enter a valid number:")
        return ENTER_MARGIN_1


async def enter_leverage_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        leverage = int(update.message.text.strip().replace('x', '').replace('X', ''))
        if leverage < 1 or leverage > 100:
            raise ValueError()
        session.trade_setup.leverage_1 = leverage
        setup = session.trade_setup
        
        await update.message.reply_text(
            f"Position 1 Complete!\\nAsset: {setup.asset_1}\\nSide: {setup.side_1.upper()}\\nMargin: ${setup.margin_1:,.2f}\\nLeverage: {leverage}x\\n\\nStep 5/9: Select Asset 2:",
            reply_markup=get_asset_keyboard())
        return SELECT_ASSET_2
    except:
        await update.message.reply_text("Invalid leverage. Enter 1-100:")
        return ENTER_LEVERAGE_1


async def select_asset_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Trade setup cancelled.")
        return ConversationHandler.END
    
    asset = query.data.replace("asset_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.asset_2 = asset
    
    await query.edit_message_text(f"Asset 2: {asset}\\n\\nStep 6/9: LONG or SHORT on {asset}?", reply_markup=get_side_keyboard())
    return SELECT_SIDE_2


async def select_side_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Trade setup cancelled.")
        return ConversationHandler.END
    
    side = query.data.replace("side_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.side_2 = side
    
    await query.edit_message_text(f"Asset 2: {session.trade_setup.asset_2} {side.upper()}\\n\\nStep 7/9: Enter margin amount in USD:")
    return ENTER_MARGIN_2


async def enter_margin_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        margin = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if margin <= 0:
            raise ValueError()
        session.trade_setup.margin_2 = margin
        
        await update.message.reply_text(f"Asset 2: {session.trade_setup.asset_2} {session.trade_setup.side_2.upper()}\\nMargin 2: ${margin:,.2f}\\n\\nStep 8/9: Enter leverage (1-100):")
        return ENTER_LEVERAGE_2
    except:
        await update.message.reply_text("Invalid amount. Enter a valid number:")
        return ENTER_MARGIN_2


async def enter_leverage_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        leverage = int(update.message.text.strip().replace('x', '').replace('X', ''))
        if leverage < 1 or leverage > 100:
            raise ValueError()
        session.trade_setup.leverage_2 = leverage
        setup = session.trade_setup
        
        await update.message.reply_text(
            f"Position 2 Complete!\\nAsset: {setup.asset_2}\\nSide: {setup.side_2.upper()}\\nMargin: ${setup.margin_2:,.2f}\\nLeverage: {leverage}x\\n\\nStep 9/9: Enter profit target in USD:")
        return ENTER_PROFIT_TARGET
    except:
        await update.message.reply_text("Invalid leverage. Enter 1-100:")
        return ENTER_LEVERAGE_2


async def enter_profit_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        target = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if target <= 0:
            raise ValueError()
        session.trade_setup.profit_target = target
        setup = session.trade_setup
        total_margin = setup.margin_1 + setup.margin_2
        
        summary = f"""Trade Setup Summary

Position 1:
Asset: {setup.asset_1}
Side: {setup.side_1.upper()}
Margin: ${setup.margin_1:,.2f}
Leverage: {setup.leverage_1}x

Position 2:
Asset: {setup.asset_2}
Side: {setup.side_2.upper()}
Margin: ${setup.margin_2:,.2f}
Leverage: {setup.leverage_2}x

Total Margin: ${total_margin:,.2f}
Profit Target: ${target:,.2f}
Auto-Reopen: Enabled

Confirm to open both positions?"""
        await update.message.reply_text(summary, reply_markup=get_confirm_keyboard())
        return CONFIRM_TRADE
    except:
        await update.message.reply_text("Invalid amount. Enter a valid number:")
        return ENTER_PROFIT_TARGET


async def confirm_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    if query.data == "confirm_no":
        await query.edit_message_text("Trade setup cancelled.")
        return ConversationHandler.END
    
    await query.edit_message_text("Opening positions...")
    client = get_lighter_client()
    setup = session.trade_setup
    
    try:
        await client.open_position(setup.asset_1, setup.side_1, setup.margin_1, setup.leverage_1)
        await client.open_position(setup.asset_2, setup.side_2, setup.margin_2, setup.leverage_2)
        
        session.trade_setup.is_active = True
        session.is_monitoring = True
        
        await context.bot.send_message(chat_id=user_id, text=f"""Positions Opened Successfully!

Position 1: {setup.asset_1} {setup.side_1.upper()}
Position 2: {setup.asset_2} {setup.side_2.upper()}

Profit Target: ${setup.profit_target:,.2f}
Monitoring started...

Use /status to check PnL
Use /panic for emergency close
Use /stop to stop monitoring""")
        
        session.monitoring_task = asyncio.create_task(monitor_positions(user_id, context))
    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"Failed to open positions: {e}")
    finally:
        await client.close()
    
    return ConversationHandler.END


async def monitor_positions(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(user_id)
    setup = session.trade_setup
    interval = int(os.getenv('MONITOR_INTERVAL', '5'))
    client = get_lighter_client()
    
    try:
        while session.is_monitoring:
            try:
                pnl_data = await client.get_total_pnl()
                current_pnl = pnl_data['unrealized_pnl']
                logger.info(f"User {user_id} - PnL: ${current_pnl:.2f} | Target: ${setup.profit_target:.2f}")
                
                if current_pnl >= setup.profit_target:
                    results = await client.close_all_positions()
                    total_pnl = sum(r.get('pnl', 0) for r in results if r.get('success'))
                    session.total_profit_booked += total_pnl
                    session.trades_completed += 1
                    
                    await context.bot.send_message(chat_id=user_id, text=f"""PROFIT TARGET REACHED!

Profit Booked: ${total_pnl:,.2f}
Total Profits: ${session.total_profit_booked:,.2f}
Trades Completed: {session.trades_completed}

Reopening positions in 5 seconds...""")
                    
                    await asyncio.sleep(5)
                    
                    if session.is_monitoring and setup.loop_enabled:
                        await client.open_position(setup.asset_1, setup.side_1, setup.margin_1, setup.leverage_1)
                        await client.open_position(setup.asset_2, setup.side_2, setup.margin_2, setup.leverage_2)
                        
                        await context.bot.send_message(chat_id=user_id, text=f"""Positions Reopened!

Position 1: {setup.asset_1} {setup.side_1.upper()}
Position 2: {setup.asset_2} {setup.side_2.upper()}

Profit Target: ${setup.profit_target:,.2f}
Monitoring resumed...""")
                
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(interval)
    finally:
        await client.close()


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return
    
    session = get_session(user_id)
    client = get_lighter_client()
    
    try:
        positions = await client.get_positions()
        pnl_data = await client.get_total_pnl()
        balance = await client.get_balance()
        
        if not positions:
            text = f"""Account Status

Balance: ${balance:,.2f}
Open Positions: 0
Session Profit: ${session.total_profit_booked:,.2f}
Trades Completed: {session.trades_completed}
Monitoring: {'Active' if session.is_monitoring else 'Inactive'}"""
        else:
            pos_text = ""
            for pos in positions:
                pos_text += f"\\n{pos.symbol} {pos.side.upper()}\\nEntry: ${pos.entry_price:,.2f} | Mark: ${pos.mark_price:,.2f}\\nPnL: ${pos.unrealized_pnl:,.2f} ({pos.pnl_percentage:+.2f}%)\\n"
            
            text = f"""Account Status

Balance: ${balance:,.2f}
{pos_text}
Total PnL: ${pnl_data['unrealized_pnl']:,.2f}
Target: ${session.trade_setup.profit_target:,.2f}
Session Profit: ${session.total_profit_booked:,.2f}
Monitoring: {'Active' if session.is_monitoring else 'Inactive'}"""
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
    finally:
        await client.close()


async def panic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return
    
    session = get_session(user_id)
    await update.message.reply_text("PANIC SELL - Closing all positions...")
    
    session.is_monitoring = False
    if session.monitoring_task:
        session.monitoring_task.cancel()
        session.monitoring_task = None
    
    client = get_lighter_client()
    try:
        results = await client.close_all_positions()
        total_pnl = sum(r.get('pnl', 0) for r in results if r.get('success'))
        session.total_profit_booked += total_pnl
        session.trade_setup.is_active = False
        
        await update.message.reply_text(f"""PANIC SELL COMPLETE

Realized PnL: ${total_pnl:,.2f}
Total Session Profit: ${session.total_profit_booked:,.2f}

Use /trade to start new setup.""")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
    finally:
        await client.close()


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return
    
    session = get_session(user_id)
    if not session.is_monitoring:
        await update.message.reply_text("Monitoring not active.")
        return
    
    session.is_monitoring = False
    if session.monitoring_task:
        session.monitoring_task.cancel()
        session.monitoring_task = None
    
    await update.message.reply_text("Monitoring Stopped\\n\\nPositions still open.\\n\\n/status - Check PnL\\n/panic - Close all\\n/trade - New setup")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""Lighter.xyz Futures Bot

Commands:
/start - Start bot
/trade - New paired trade
/status - Check PnL
/panic - Emergency close
/stop - Stop monitoring
/help - This message""")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Cancelled.")
    else:
        await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def set_commands(application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("trade", "New paired trade"),
        BotCommand("status", "Check PnL"),
        BotCommand("panic", "Emergency close all"),
        BotCommand("stop", "Stop monitoring"),
        BotCommand("help", "Help"),
    ]
    await application.bot.set_my_commands(commands)


def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token or token == 'your_telegram_bot_token_here':
        print("\\nSet TELEGRAM_BOT_TOKEN in .env file")
        return
    
    application = Application.builder().token(token).build()
    
    trade_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CommandHandler('trade', trade_command)],
        states={
            SELECT_ASSET_1: [CallbackQueryHandler(select_asset_1)],
            SELECT_SIDE_1: [CallbackQueryHandler(select_side_1)],
            ENTER_MARGIN_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_margin_1)],
            ENTER_LEVERAGE_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_leverage_1)],
            SELECT_ASSET_2: [CallbackQueryHandler(select_asset_2)],
            SELECT_SIDE_2: [CallbackQueryHandler(select_side_2)],
            ENTER_MARGIN_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_margin_2)],
            ENTER_LEVERAGE_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_leverage_2)],
            ENTER_PROFIT_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_profit_target)],
            CONFIRM_TRADE: [CallbackQueryHandler(confirm_trade)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    
    application.add_handler(trade_handler)
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('panic', panic_command))
    application.add_handler(CommandHandler('stop', stop_command))
    application.add_handler(CommandHandler('help', help_command))
    application.post_init = set_commands
    
    print("\\nLighter.xyz Futures Bot Started!\\nPress Ctrl+C to stop\\n")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
'''


def main():
    print("Creating bot files...")
    print()
    
    for filename, content in FILES.items():
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Created: {filename}")
    
    print()
    print("All files created successfully!")
    print()
    print("Next steps:")
    print("  1. Copy .env.example to .env")
    print("     cp .env.example .env")
    print()
    print("  2. Edit .env and add your credentials")
    print()
    print("  3. Install dependencies:")
    print("     pip install -r requirements.txt")
    print()
    print("  4. Run the bot:")
    print("     python bot.py")
    print()


if __name__ == '__main__':
    main()
