#!/bin/bash
# Lighter.xyz Futures Bot - Server Deployment Script

echo "========================================"
echo "Lighter.xyz Futures Bot Deployment"
echo "========================================"

# Create directory
mkdir -p /opt/lighter-bot
cd /opt/lighter-bot

# Create .env file
cat > .env << 'ENVEOF'
USE_MOCK=false
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_TOKEN_HERE
LIGHTER_PRIVATE_KEY=YOUR_80_CHAR_PRIVATE_KEY_HERE
ACCOUNT_INDEX=703156
API_KEY_INDEX=4
LIGHTER_BASE_URL=https://mainnet.zklighter.elliot.ai
MONITOR_INTERVAL=5
ENVEOF

echo "Created .env file - EDIT IT with your credentials!"
echo ""

# Create lighter_client_v2.py
cat > lighter_client_v2.py << 'CLIENTEOF'
"""
Lighter.xyz API Client for Futures Trading
"""
import os
import time
import logging
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import random

logger = logging.getLogger(__name__)

try:
    import lighter
    from lighter import ApiClient, Configuration, AccountApi, OrderApi, TransactionApi
    LIGHTER_SDK_AVAILABLE = True
except ImportError:
    LIGHTER_SDK_AVAILABLE = False
    logger.warning("Lighter SDK not installed")


@dataclass
class Position:
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
    order_index: Optional[int] = None
    
    @property
    def pnl_percentage(self) -> float:
        if self.margin == 0:
            return 0.0
        return (self.unrealized_pnl / self.margin) * 100


class LighterClient:
    SUPPORTED_ASSETS = ['BTC', 'ETH', 'SOL']
    MARKET_IDS = {'BTC': 1, 'ETH': 0, 'SOL': 2}
    SIZE_DECIMALS = {'BTC': 5, 'ETH': 4, 'SOL': 3}
    PRICE_DECIMALS = {'BTC': 1, 'ETH': 2, 'SOL': 3}
    
    def __init__(self, base_url: str, private_key: str, account_index: int, api_key_index: int = 10):
        self.base_url = base_url
        self.private_key = private_key
        self.account_index = account_index
        self.api_key_index = api_key_index
        self._signer_client = None
        self._api_client = None
        self._account_api = None
        self._order_api = None
        self._positions: Dict[str, Position] = {}
        self._order_counter = int(time.time())
        self._initialize_client()
    
    def _initialize_client(self):
        if not LIGHTER_SDK_AVAILABLE:
            raise Exception("Lighter SDK not installed")
        try:
            pk = self.private_key.strip()
            if pk.startswith("0x"):
                pk = pk[2:]
            logger.info(f"Initializing Lighter client...")
            self._signer_client = lighter.SignerClient(
                url=self.base_url,
                api_private_keys={self.api_key_index: pk},
                account_index=self.account_index
            )
            config = Configuration(host=self.base_url)
            self._api_client = ApiClient(config)
            self._account_api = AccountApi(self._api_client)
            self._order_api = OrderApi(self._api_client)
            logger.info("LIGHTER CLIENT INITIALIZED SUCCESSFULLY")
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            raise
    
    async def close(self):
        if self._api_client:
            await self._api_client.close()
    
    async def get_account_info(self) -> Dict[str, Any]:
        try:
            account = await self._account_api.account(self.account_index)
            return {'index': getattr(account, 'index', self.account_index), 'collateral': float(getattr(account, 'collateral', 0))}
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {'index': self.account_index, 'collateral': 0}
    
    async def get_balance(self) -> float:
        try:
            info = await self.get_account_info()
            return info.get('collateral', 0.0)
        except:
            return 0.0
    
    async def get_mark_price(self, symbol: str) -> float:
        try:
            market_id = self.MARKET_IDS.get(symbol.upper(), 1)
            result = await self._order_api.order_book_details(market_id=market_id)
            if result and hasattr(result, 'order_book_details') and result.order_book_details:
                ob = result.order_book_details[0]
                if hasattr(ob, 'last_trade_price') and ob.last_trade_price:
                    price = float(ob.last_trade_price)
                    logger.info(f"Got price for {symbol}: ${price:,.2f}")
                    return price
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get mark price: {e}")
            return 0.0
    
    async def get_positions(self) -> List[Position]:
        for symbol, pos in self._positions.items():
            price = await self.get_mark_price(symbol)
            if price > 0:
                pos.mark_price = price
                diff = price - pos.entry_price
                if pos.side == 'short':
                    diff = -diff
                pos.unrealized_pnl = (diff / pos.entry_price) * pos.margin * pos.leverage
        return list(self._positions.values())
    
    async def open_position(self, symbol: str, side: str, margin: float, leverage: int) -> Dict[str, Any]:
        try:
            market_id = self.MARKET_IDS.get(symbol.upper(), 1)
            size_decimals = self.SIZE_DECIMALS.get(symbol.upper(), 5)
            price_decimals = self.PRICE_DECIMALS.get(symbol.upper(), 1)
            mark_price = await self.get_mark_price(symbol)
            if mark_price <= 0:
                raise Exception(f"Could not get valid price for {symbol}")
            
            margin_mode = 0
            logger.info(f"Setting leverage to {leverage}x for {symbol}")
            try:
                await self._signer_client.update_leverage(market_id, margin_mode, leverage)
                logger.info(f"Leverage set successfully to {leverage}x")
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.warning(f"Could not set leverage: {e}")
                await asyncio.sleep(1.5)
            
            notional_value = margin * leverage
            size = notional_value / mark_price
            base_amount = int(size * (10 ** size_decimals))
            is_ask = side.lower() != 'long'
            
            if is_ask:
                price_with_slippage = mark_price * 0.98
            else:
                price_with_slippage = mark_price * 1.02
            price_int = int(price_with_slippage * (10 ** price_decimals))
            
            self._order_counter += 1
            client_order_index = self._order_counter
            
            logger.info(f"Opening {side} {symbol}: Margin=${margin}, Leverage={leverage}x, Size={size:.6f}")
            
            result = await self._signer_client.create_market_order(
                market_id, client_order_index, base_amount, price_int, is_ask, False
            )
            
            pos = Position(
                symbol=symbol.upper(), side=side.lower(), size=size,
                entry_price=mark_price, mark_price=mark_price, leverage=leverage,
                margin=margin, unrealized_pnl=0.0, realized_pnl=0.0,
                liquidation_price=mark_price * (0.5 if side == 'long' else 1.5),
                position_id=f"{symbol}_{client_order_index}", order_index=client_order_index
            )
            self._positions[symbol.upper()] = pos
            logger.info(f"Position opened: {result}")
            await asyncio.sleep(1.5)
            return {'success': True, 'order_index': client_order_index}
        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            await asyncio.sleep(1.5)
            raise
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        pos = self._positions.get(symbol.upper())
        if not pos:
            raise Exception(f"No position for {symbol}")
        try:
            market_id = self.MARKET_IDS.get(symbol.upper(), 1)
            size_decimals = self.SIZE_DECIMALS.get(symbol.upper(), 5)
            price_decimals = self.PRICE_DECIMALS.get(symbol.upper(), 1)
            mark_price = await self.get_mark_price(symbol)
            diff = mark_price - pos.entry_price
            if pos.side == 'short':
                diff = -diff
            pnl = (diff / pos.entry_price) * pos.margin * pos.leverage
            base_amount = int(pos.size * (10 ** size_decimals))
            is_ask = pos.side == 'long'
            if is_ask:
                price_with_slippage = mark_price * 0.98
            else:
                price_with_slippage = mark_price * 1.02
            price_int = int(price_with_slippage * (10 ** price_decimals))
            self._order_counter += 1
            logger.info(f"Closing {pos.side} {symbol}: size={pos.size:.6f}")
            result = await self._signer_client.create_market_order(
                market_id, self._order_counter, base_amount, price_int, is_ask, True
            )
            del self._positions[symbol.upper()]
            logger.info(f"Position closed: PnL=${pnl:,.2f}")
            return {'success': True, 'pnl': pnl}
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            raise
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        results = []
        for symbol in list(self._positions.keys()):
            try:
                r = await self.close_position(symbol)
                results.append({'symbol': symbol, 'success': True, 'pnl': r.get('pnl', 0)})
                await asyncio.sleep(1.5)
            except Exception as e:
                results.append({'symbol': symbol, 'success': False, 'error': str(e)})
        return results
    
    async def get_total_pnl(self) -> Dict[str, float]:
        positions = await self.get_positions()
        total_pnl = sum(p.unrealized_pnl for p in positions)
        total_margin = sum(p.margin for p in positions)
        return {
            'unrealized_pnl': total_pnl, 'realized_pnl': 0, 'total_pnl': total_pnl,
            'total_margin': total_margin,
            'pnl_percentage': (total_pnl / total_margin * 100) if total_margin > 0 else 0
        }


class MockLighterClient:
    SUPPORTED_ASSETS = ['BTC', 'ETH', 'SOL']
    MARKET_IDS = {'BTC': 1, 'ETH': 0, 'SOL': 2}
    
    def __init__(self, *args, **kwargs):
        self._positions: Dict[str, Position] = {}
        self._balance = 10000.0
        self._prices = {'BTC': 95000.0, 'ETH': 3200.0, 'SOL': 180.0}
        self._counter = int(time.time())
        logger.info("MOCK MODE - No real trades")
    
    async def close(self): pass
    async def get_balance(self) -> float: return self._balance
    
    async def get_mark_price(self, symbol: str) -> float:
        base = self._prices.get(symbol.upper(), 100.0)
        self._prices[symbol.upper()] = base * (1 + random.uniform(-0.005, 0.006))
        return self._prices[symbol.upper()]
    
    async def get_positions(self) -> List[Position]:
        for pos in self._positions.values():
            price = await self.get_mark_price(pos.symbol)
            pos.mark_price = price
            diff = price - pos.entry_price
            if pos.side == 'short': diff = -diff
            pos.unrealized_pnl = (diff / pos.entry_price) * pos.margin * pos.leverage
        return list(self._positions.values())
    
    async def open_position(self, symbol: str, side: str, margin: float, leverage: int) -> Dict[str, Any]:
        price = await self.get_mark_price(symbol)
        size = (margin * leverage) / price
        self._counter += 1
        pos = Position(symbol=symbol.upper(), side=side.lower(), size=size, entry_price=price,
                      mark_price=price, leverage=leverage, margin=margin, unrealized_pnl=0,
                      realized_pnl=0, liquidation_price=price*(0.5 if side=='long' else 1.5),
                      position_id=f"MOCK_{self._counter}")
        self._positions[symbol.upper()] = pos
        self._balance -= margin
        logger.info(f"[MOCK] Opened {side} {symbol} @ ${price:,.2f}")
        return {'success': True}
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        pos = self._positions.get(symbol.upper())
        if not pos: raise Exception(f"No position for {symbol}")
        price = await self.get_mark_price(symbol)
        diff = price - pos.entry_price
        if pos.side == 'short': diff = -diff
        pnl = (diff / pos.entry_price) * pos.margin * pos.leverage
        self._balance += pos.margin + pnl
        del self._positions[symbol.upper()]
        logger.info(f"[MOCK] Closed {symbol} PnL: ${pnl:,.2f}")
        return {'success': True, 'pnl': pnl}
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        results = []
        for symbol in list(self._positions.keys()):
            try:
                r = await self.close_position(symbol)
                results.append({'symbol': symbol, 'success': True, 'pnl': r['pnl']})
            except Exception as e:
                results.append({'symbol': symbol, 'success': False, 'error': str(e)})
        return results
    
    async def get_total_pnl(self) -> Dict[str, float]:
        await self.get_positions()
        total = sum(p.unrealized_pnl for p in self._positions.values())
        margin = sum(p.margin for p in self._positions.values())
        return {'unrealized_pnl': total, 'realized_pnl': 0, 'total_pnl': total,
                'total_margin': margin, 'pnl_percentage': (total/margin*100) if margin > 0 else 0}
CLIENTEOF

echo "Created lighter_client_v2.py"

# Create bot_v2.py
cat > bot_v2.py << 'BOTEOF'
"""
Lighter.xyz Futures Trading Telegram Bot
"""
import os
import asyncio
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          ConversationHandler, MessageHandler, ContextTypes, filters)
from lighter_client_v2 import LighterClient, MockLighterClient

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
_lighter_client = None

def get_session(user_id: int) -> UserSession:
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()
    return user_sessions[user_id]

def get_lighter_client():
    global _lighter_client
    use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
    if use_mock:
        logger.info("Using MOCK client")
        return MockLighterClient()
    private_key = os.getenv('LIGHTER_PRIVATE_KEY', '') or os.getenv('ETH_PRIVATE_KEY', '')
    account_index = os.getenv('ACCOUNT_INDEX', '')
    api_key_index = int(os.getenv('API_KEY_INDEX', '10'))
    base_url = os.getenv('LIGHTER_BASE_URL', 'https://mainnet.zklighter.elliot.ai')
    if not private_key or not account_index:
        logger.warning("Missing credentials, using MOCK client")
        return MockLighterClient()
    if _lighter_client is None:
        try:
            _lighter_client = LighterClient(base_url=base_url, private_key=private_key,
                                           account_index=int(account_index), api_key_index=api_key_index)
            logger.info("LIVE MODE - Connected to Lighter.xyz")
        except Exception as e:
            logger.error(f"Failed to create client: {e}")
            return MockLighterClient()
    return _lighter_client

def is_user_authorized(user_id: int) -> bool:
    allowed_ids = os.getenv('ALLOWED_USER_IDS', '')
    if not allowed_ids: return True
    allowed_list = [int(uid.strip()) for uid in allowed_ids.split(',') if uid.strip()]
    return user_id in allowed_list

def get_asset_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("BTC", callback_data="asset_BTC"),
         InlineKeyboardButton("ETH", callback_data="asset_ETH"),
         InlineKeyboardButton("SOL", callback_data="asset_SOL")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])

def get_side_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("LONG", callback_data="side_long"),
         InlineKeyboardButton("SHORT", callback_data="side_short")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])

def get_confirm_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Confirm", callback_data="confirm_yes"),
        InlineKeyboardButton("Cancel", callback_data="confirm_no")
    ]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END
    get_session(user_id)
    use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
    mode = "MOCK MODE" if use_mock else "LIVE TRADING"
    await update.message.reply_text(f"Lighter.xyz Bot ({mode})\n\nCommands:\n/trade - New trade\n/status - Check PnL\n/panic - Close all\n/stop - Stop monitoring\n\nSelect Asset 1:", reply_markup=get_asset_keyboard())
    return SELECT_ASSET_1

async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END
    session = get_session(user_id)
    if session.is_monitoring:
        await update.message.reply_text("Trade already active. Use /stop or /panic first.")
        return ConversationHandler.END
    session.trade_setup = TradeSetup()
    await update.message.reply_text("New Trade Setup\n\nStep 1/9: Select Asset 1:", reply_markup=get_asset_keyboard())
    return SELECT_ASSET_1

async def select_asset_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END
    asset = query.data.replace("asset_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.asset_1 = asset
    await query.edit_message_text(f"Asset 1: {asset}\n\nStep 2/9: LONG or SHORT?", reply_markup=get_side_keyboard())
    return SELECT_SIDE_1

async def select_side_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END
    side = query.data.replace("side_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.side_1 = side
    await query.edit_message_text(f"Asset 1: {session.trade_setup.asset_1} {side.upper()}\n\nStep 3/9: Enter margin in USD:")
    return ENTER_MARGIN_1

async def enter_margin_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        margin = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if margin <= 0: raise ValueError()
        session.trade_setup.margin_1 = margin
        await update.message.reply_text(f"Margin 1: ${margin:.2f}\n\nStep 4/9: Enter leverage (1-100):")
        return ENTER_LEVERAGE_1
    except:
        await update.message.reply_text("Invalid. Enter a number:")
        return ENTER_MARGIN_1

async def enter_leverage_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        leverage = int(update.message.text.strip().replace('x', ''))
        if leverage < 1 or leverage > 100: raise ValueError()
        session.trade_setup.leverage_1 = leverage
        setup = session.trade_setup
        await update.message.reply_text(f"Position 1: {setup.asset_1} {setup.side_1.upper()}\nMargin: ${setup.margin_1:.2f}, Leverage: {leverage}x\n\nStep 5/9: Select Asset 2:", reply_markup=get_asset_keyboard())
        return SELECT_ASSET_2
    except:
        await update.message.reply_text("Invalid. Enter 1-100:")
        return ENTER_LEVERAGE_1

async def select_asset_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END
    asset = query.data.replace("asset_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.asset_2 = asset
    await query.edit_message_text(f"Asset 2: {asset}\n\nStep 6/9: LONG or SHORT?", reply_markup=get_side_keyboard())
    return SELECT_SIDE_2

async def select_side_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END
    side = query.data.replace("side_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.side_2 = side
    await query.edit_message_text(f"Asset 2: {session.trade_setup.asset_2} {side.upper()}\n\nStep 7/9: Enter margin in USD:")
    return ENTER_MARGIN_2

async def enter_margin_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        margin = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if margin <= 0: raise ValueError()
        session.trade_setup.margin_2 = margin
        await update.message.reply_text(f"Margin 2: ${margin:.2f}\n\nStep 8/9: Enter leverage (1-100):")
        return ENTER_LEVERAGE_2
    except:
        await update.message.reply_text("Invalid. Enter a number:")
        return ENTER_MARGIN_2

async def enter_leverage_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        leverage = int(update.message.text.strip().replace('x', ''))
        if leverage < 1 or leverage > 100: raise ValueError()
        session.trade_setup.leverage_2 = leverage
        await update.message.reply_text(f"Position 2 set.\n\nStep 9/9: Enter profit target in USD:")
        return ENTER_PROFIT_TARGET
    except:
        await update.message.reply_text("Invalid. Enter 1-100:")
        return ENTER_LEVERAGE_2

async def enter_profit_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        target = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if target <= 0: raise ValueError()
        session.trade_setup.profit_target = target
        setup = session.trade_setup
        total_margin = setup.margin_1 + setup.margin_2
        summary = f"SUMMARY\n\nPos 1: {setup.asset_1} {setup.side_1.upper()} ${setup.margin_1:.2f} {setup.leverage_1}x\nPos 2: {setup.asset_2} {setup.side_2.upper()} ${setup.margin_2:.2f} {setup.leverage_2}x\n\nTotal Margin: ${total_margin:.2f}\nProfit Target: ${target:.2f}\n\nConfirm?"
        await update.message.reply_text(summary, reply_markup=get_confirm_keyboard())
        return CONFIRM_TRADE
    except:
        await update.message.reply_text("Invalid. Enter a number:")
        return ENTER_PROFIT_TARGET

async def confirm_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_session(user_id)
    if query.data == "confirm_no":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END
    await query.edit_message_text("Opening positions...")
    client = get_lighter_client()
    setup = session.trade_setup
    try:
        await client.open_position(setup.asset_1, setup.side_1, setup.margin_1, setup.leverage_1)
        await client.open_position(setup.asset_2, setup.side_2, setup.margin_2, setup.leverage_2)
        session.trade_setup.is_active = True
        session.is_monitoring = True
        await context.bot.send_message(chat_id=user_id, text=f"Positions Opened!\n\nPos 1: {setup.asset_1} {setup.side_1.upper()}\nPos 2: {setup.asset_2} {setup.side_2.upper()}\n\nTarget: ${setup.profit_target:.2f}\nMonitoring...\n\n/status /panic /stop")
        session.monitoring_task = asyncio.create_task(monitor_positions(user_id, context))
    except Exception as e:
        logger.error(f"Failed: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"Failed: {e}")
    return ConversationHandler.END

async def monitor_positions(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(user_id)
    setup = session.trade_setup
    interval = int(os.getenv('MONITOR_INTERVAL', '5'))
    client = get_lighter_client()
    logger.info(f"Monitoring | Target: ${setup.profit_target}")
    try:
        count = 0
        while session.is_monitoring:
            try:
                count += 1
                pnl_data = await client.get_total_pnl()
                pnl = pnl_data['unrealized_pnl']
                emoji = "+" if pnl >= 0 else ""
                logger.info(f"[#{count}] PnL: {emoji}${pnl:.2f} | Target: ${setup.profit_target:.2f}")
                if pnl >= setup.profit_target:
                    logger.info("TARGET REACHED!")
                    results = await client.close_all_positions()
                    total_pnl = sum(r.get('pnl', 0) for r in results if r.get('success'))
                    session.total_profit_booked += total_pnl
                    session.trades_completed += 1
                    await context.bot.send_message(chat_id=user_id, text=f"TARGET REACHED!\n\nProfit: ${total_pnl:.2f}\nTotal: ${session.total_profit_booked:.2f}\nTrades: {session.trades_completed}\n\nReopening in 5s...")
                    await asyncio.sleep(5)
                    if session.is_monitoring and setup.loop_enabled:
                        await client.open_position(setup.asset_1, setup.side_1, setup.margin_1, setup.leverage_1)
                        await client.open_position(setup.asset_2, setup.side_2, setup.margin_2, setup.leverage_2)
                        await context.bot.send_message(chat_id=user_id, text=f"Positions Reopened!\n\nTarget: ${setup.profit_target:.2f}")
                        count = 0
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(interval)
    finally:
        logger.info("Monitoring stopped")

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
            text = f"Balance: ${balance:.2f}\nPositions: 0\nSession Profit: ${session.total_profit_booked:.2f}\nMonitoring: {'Yes' if session.is_monitoring else 'No'}"
        else:
            pos_text = ""
            for pos in positions:
                emoji = "+" if pos.unrealized_pnl >= 0 else ""
                pos_text += f"\n{pos.symbol} {pos.side.upper()}: {emoji}${pos.unrealized_pnl:.2f}"
            text = f"Balance: ${balance:.2f}{pos_text}\n\nTotal PnL: ${pnl_data['unrealized_pnl']:.2f}\nTarget: ${session.trade_setup.profit_target:.2f}\nSession Profit: ${session.total_profit_booked:.2f}"
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def panic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return
    session = get_session(user_id)
    await update.message.reply_text("PANIC - Closing all...")
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
        await update.message.reply_text(f"CLOSED\n\nPnL: ${total_pnl:.2f}\nTotal: ${session.total_profit_booked:.2f}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return
    session = get_session(user_id)
    if not session.is_monitoring:
        await update.message.reply_text("Not monitoring.")
        return
    session.is_monitoring = False
    if session.monitoring_task:
        session.monitoring_task.cancel()
        session.monitoring_task = None
    await update.message.reply_text("Stopped monitoring.\nPositions still open.\n\n/status /panic /trade")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commands:\n/start - Start\n/trade - New trade\n/status - Check PnL\n/panic - Close all\n/stop - Stop monitoring")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Cancelled.")
    else:
        await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

async def set_commands(application):
    commands = [BotCommand("start", "Start"), BotCommand("trade", "New trade"),
                BotCommand("status", "Check PnL"), BotCommand("panic", "Close all"),
                BotCommand("stop", "Stop monitoring"), BotCommand("help", "Help")]
    await application.bot.set_my_commands(commands)

def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("Set TELEGRAM_BOT_TOKEN in .env")
        return
    use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
    print(f"\nLighter.xyz Bot - {'MOCK' if use_mock else 'LIVE'} mode\n")
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
        per_message=False
    )
    application.add_handler(trade_handler)
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('panic', panic_command))
    application.add_handler(CommandHandler('stop', stop_command))
    application.add_handler(CommandHandler('help', help_command))
    application.post_init = set_commands
    print("Press Ctrl+C to stop\n")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
BOTEOF

echo "Created bot_v2.py"

# Create systemd service
cat > /etc/systemd/system/lighter-bot.service << 'SERVICEEOF'
[Unit]
Description=Lighter.xyz Futures Trading Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/lighter-bot
Environment=PATH=/opt/lighter-bot/venv/bin
ExecStart=/opt/lighter-bot/venv/bin/python bot_v2.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

echo "Created systemd service"

echo ""
echo "========================================"
echo "DEPLOYMENT COMPLETE!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Edit /opt/lighter-bot/.env with your credentials:"
echo "   nano /opt/lighter-bot/.env"
echo ""
echo "2. Install dependencies:"
echo "   cd /opt/lighter-bot"
echo "   python3 -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install python-telegram-bot==21.7 python-dotenv aiohttp lighter-sdk"
echo ""
echo "3. Start the bot:"
echo "   systemctl daemon-reload"
echo "   systemctl enable lighter-bot"
echo "   systemctl start lighter-bot"
echo ""
echo "4. Check status:"
echo "   systemctl status lighter-bot"
echo "   journalctl -u lighter-bot -f"
echo ""
