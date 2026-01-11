"""
Lighter.xyz Futures Trading Telegram Bot

A comprehensive Telegram bot for managing futures trades on app.lighter.xyz
with support for hedging strategies across multiple assets.
"""
import os
import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from decimal import Decimal

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from lighter_client import LighterClient, MockLighterClient, Position

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    SELECT_ASSET_1,
    SELECT_SIDE_1,
    ENTER_MARGIN_1,
    ENTER_LEVERAGE_1,
    SELECT_ASSET_2,
    SELECT_SIDE_2,
    ENTER_MARGIN_2,
    ENTER_LEVERAGE_2,
    ENTER_PROFIT_TARGET,
    CONFIRM_TRADE
) = range(10)


@dataclass
class TradeSetup:
    """Holds the configuration for a paired trade"""
    # First position
    asset_1: str = ""
    side_1: str = ""  # 'long' or 'short'
    margin_1: float = 0.0
    leverage_1: int = 1
    
    # Second position
    asset_2: str = ""
    side_2: str = ""
    margin_2: float = 0.0
    leverage_2: int = 1
    
    # Profit target
    profit_target: float = 0.0
    
    # State
    is_active: bool = False
    loop_enabled: bool = True


@dataclass
class UserSession:
    """Holds user-specific session data"""
    trade_setup: TradeSetup = field(default_factory=TradeSetup)
    monitoring_task: Optional[asyncio.Task] = None
    is_monitoring: bool = False
    total_profit_booked: float = 0.0
    trades_completed: int = 0


# Store user sessions
user_sessions: Dict[int, UserSession] = {}


def get_session(user_id: int) -> UserSession:
    """Get or create user session"""
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()
    return user_sessions[user_id]


def get_lighter_client() -> LighterClient:
    """Create and return a Lighter client instance"""
    api_key = os.getenv('LIGHTER_API_KEY', '')
    api_secret = os.getenv('LIGHTER_API_SECRET', '')
    wallet_address = os.getenv('LIGHTER_WALLET_ADDRESS', '')
    base_url = os.getenv('LIGHTER_API_URL', 'https://api.lighter.xyz')
    
    # Use mock client if credentials not provided
    if not api_key or api_key == 'your_lighter_api_key_here':
        logger.warning("Using mock client - no API credentials provided")
        return MockLighterClient(api_key, api_secret, wallet_address, base_url)
    
    return LighterClient(api_key, api_secret, wallet_address, base_url)


def is_user_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot"""
    allowed_ids = os.getenv('ALLOWED_USER_IDS', '')
    if not allowed_ids or allowed_ids == 'your_telegram_user_id':
        return True  # Allow all if not configured
    
    allowed_list = [int(uid.strip()) for uid in allowed_ids.split(',') if uid.strip()]
    return user_id in allowed_list


def get_asset_keyboard() -> InlineKeyboardMarkup:
    """Create asset selection keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("₿ BTC", callback_data="asset_BTC"),
            InlineKeyboardButton("Ξ ETH", callback_data="asset_ETH"),
            InlineKeyboardButton("◎ SOL", callback_data="asset_SOL")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_side_keyboard() -> InlineKeyboardMarkup:
    """Create long/short selection keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📈 LONG", callback_data="side_long"),
            InlineKeyboardButton("📉 SHORT", callback_data="side_short")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Create confirmation keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm & Start", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="confirm_no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the bot and show main menu"""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return ConversationHandler.END
    
    session = get_session(user_id)
    
    welcome_text = """
🤖 **Lighter.xyz Futures Trading Bot**

Welcome! This bot helps you execute paired futures trades on app.lighter.xyz

📋 **Commands:**
• /trade - Start new paired trade setup
• /status - Check current PnL
• /panic - Market sell all positions
• /stop - Stop monitoring

Let's set up your paired trade! You'll configure two positions that will be opened simultaneously.

Select **Asset 1** to begin:
"""
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_asset_keyboard()
    )
    
    return SELECT_ASSET_1


async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start a new trade setup"""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return ConversationHandler.END
    
    session = get_session(user_id)
    
    # Check if already monitoring
    if session.is_monitoring:
        await update.message.reply_text(
            "⚠️ A trade is already active. Use /stop to stop monitoring first, or /panic to close all positions."
        )
        return ConversationHandler.END
    
    # Reset trade setup
    session.trade_setup = TradeSetup()
    
    await update.message.reply_text(
        "🔄 **New Paired Trade Setup**\n\n"
        "Step 1/9: Select **Asset 1**:",
        parse_mode='Markdown',
        reply_markup=get_asset_keyboard()
    )
    
    return SELECT_ASSET_1


async def select_asset_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle first asset selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    asset = query.data.replace("asset_", "")
    user_id = update.effective_user.id
    session = get_session(user_id)
    session.trade_setup.asset_1 = asset
    
    await query.edit_message_text(
        f"✅ Asset 1: **{asset}**\n\n"
        f"Step 2/9: Are you going **LONG** or **SHORT** on {asset}?",
        parse_mode='Markdown',
        reply_markup=get_side_keyboard()
    )
    
    return SELECT_SIDE_1


async def select_side_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle first position side selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    side = query.data.replace("side_", "")
    user_id = update.effective_user.id
    session = get_session(user_id)
    session.trade_setup.side_1 = side
    
    side_emoji = "📈" if side == "long" else "📉"
    
    await query.edit_message_text(
        f"✅ Asset 1: **{session.trade_setup.asset_1}** {side_emoji} {side.upper()}\n\n"
        f"Step 3/9: Enter **margin amount** in USD for Position 1:\n"
        f"(Example: 100)",
        parse_mode='Markdown'
    )
    
    return ENTER_MARGIN_1


async def enter_margin_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle first margin input"""
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    try:
        margin = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if margin <= 0:
            raise ValueError("Margin must be positive")
        
        session.trade_setup.margin_1 = margin
        
        side_emoji = "📈" if session.trade_setup.side_1 == "long" else "📉"
        
        await update.message.reply_text(
            f"✅ Asset 1: **{session.trade_setup.asset_1}** {side_emoji} {session.trade_setup.side_1.upper()}\n"
            f"✅ Margin 1: **${margin:,.2f}**\n\n"
            f"Step 4/9: Enter **leverage** for Position 1:\n"
            f"(1-100, Example: 10)",
            parse_mode='Markdown'
        )
        
        return ENTER_LEVERAGE_1
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a valid number (e.g., 100 or 500.50):"
        )
        return ENTER_MARGIN_1


async def enter_leverage_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle first leverage input"""
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    try:
        leverage = int(update.message.text.strip().replace('x', '').replace('X', ''))
        if leverage < 1 or leverage > 100:
            raise ValueError("Leverage must be between 1 and 100")
        
        session.trade_setup.leverage_1 = leverage
        
        side_emoji = "📈" if session.trade_setup.side_1 == "long" else "📉"
        
        await update.message.reply_text(
            f"✅ **Position 1 Complete!**\n"
            f"   Asset: {session.trade_setup.asset_1}\n"
            f"   Side: {side_emoji} {session.trade_setup.side_1.upper()}\n"
            f"   Margin: ${session.trade_setup.margin_1:,.2f}\n"
            f"   Leverage: {leverage}x\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Step 5/9: Now select **Asset 2**:",
            parse_mode='Markdown',
            reply_markup=get_asset_keyboard()
        )
        
        return SELECT_ASSET_2
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid leverage. Please enter a number between 1 and 100:"
        )
        return ENTER_LEVERAGE_1


async def select_asset_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle second asset selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    asset = query.data.replace("asset_", "")
    user_id = update.effective_user.id
    session = get_session(user_id)
    session.trade_setup.asset_2 = asset
    
    await query.edit_message_text(
        f"✅ Asset 2: **{asset}**\n\n"
        f"Step 6/9: Are you going **LONG** or **SHORT** on {asset}?",
        parse_mode='Markdown',
        reply_markup=get_side_keyboard()
    )
    
    return SELECT_SIDE_2


async def select_side_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle second position side selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    side = query.data.replace("side_", "")
    user_id = update.effective_user.id
    session = get_session(user_id)
    session.trade_setup.side_2 = side
    
    side_emoji = "📈" if side == "long" else "📉"
    
    await query.edit_message_text(
        f"✅ Asset 2: **{session.trade_setup.asset_2}** {side_emoji} {side.upper()}\n\n"
        f"Step 7/9: Enter **margin amount** in USD for Position 2:\n"
        f"(Example: 100)",
        parse_mode='Markdown'
    )
    
    return ENTER_MARGIN_2


async def enter_margin_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle second margin input"""
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    try:
        margin = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if margin <= 0:
            raise ValueError("Margin must be positive")
        
        session.trade_setup.margin_2 = margin
        
        side_emoji = "📈" if session.trade_setup.side_2 == "long" else "📉"
        
        await update.message.reply_text(
            f"✅ Asset 2: **{session.trade_setup.asset_2}** {side_emoji} {session.trade_setup.side_2.upper()}\n"
            f"✅ Margin 2: **${margin:,.2f}**\n\n"
            f"Step 8/9: Enter **leverage** for Position 2:\n"
            f"(1-100, Example: 10)",
            parse_mode='Markdown'
        )
        
        return ENTER_LEVERAGE_2
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a valid number (e.g., 100 or 500.50):"
        )
        return ENTER_MARGIN_2


async def enter_leverage_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle second leverage input"""
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    try:
        leverage = int(update.message.text.strip().replace('x', '').replace('X', ''))
        if leverage < 1 or leverage > 100:
            raise ValueError("Leverage must be between 1 and 100")
        
        session.trade_setup.leverage_2 = leverage
        
        side_emoji = "📈" if session.trade_setup.side_2 == "long" else "📉"
        
        await update.message.reply_text(
            f"✅ **Position 2 Complete!**\n"
            f"   Asset: {session.trade_setup.asset_2}\n"
            f"   Side: {side_emoji} {session.trade_setup.side_2.upper()}\n"
            f"   Margin: ${session.trade_setup.margin_2:,.2f}\n"
            f"   Leverage: {leverage}x\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Step 9/9: Enter your **profit target** in USD:\n"
            f"(Example: 50)",
            parse_mode='Markdown'
        )
        
        return ENTER_PROFIT_TARGET
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid leverage. Please enter a number between 1 and 100:"
        )
        return ENTER_LEVERAGE_2


async def enter_profit_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle profit target input"""
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    try:
        target = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if target <= 0:
            raise ValueError("Target must be positive")
        
        session.trade_setup.profit_target = target
        
        # Show summary
        setup = session.trade_setup
        side1_emoji = "📈" if setup.side_1 == "long" else "📉"
        side2_emoji = "📈" if setup.side_2 == "long" else "📉"
        
        total_margin = setup.margin_1 + setup.margin_2
        
        summary = f"""
📋 **Trade Setup Summary**

**Position 1:**
• Asset: {setup.asset_1}
• Side: {side1_emoji} {setup.side_1.upper()}
• Margin: ${setup.margin_1:,.2f}
• Leverage: {setup.leverage_1}x
• Notional: ${setup.margin_1 * setup.leverage_1:,.2f}

**Position 2:**
• Asset: {setup.asset_2}
• Side: {side2_emoji} {setup.side_2.upper()}
• Margin: ${setup.margin_2:,.2f}
• Leverage: {setup.leverage_2}x
• Notional: ${setup.margin_2 * setup.leverage_2:,.2f}

━━━━━━━━━━━━━━━━━━━━━━
💰 **Total Margin:** ${total_margin:,.2f}
🎯 **Profit Target:** ${target:,.2f}
🔄 **Auto-Reopen:** Enabled

Confirm to open both positions?
"""
        
        await update.message.reply_text(
            summary,
            parse_mode='Markdown',
            reply_markup=get_confirm_keyboard()
        )
        
        return CONFIRM_TRADE
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a valid number (e.g., 50 or 100.50):"
        )
        return ENTER_PROFIT_TARGET


async def confirm_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle trade confirmation"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    if query.data == "confirm_no":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    # Execute trades
    await query.edit_message_text("⏳ Opening positions...")
    
    client = get_lighter_client()
    setup = session.trade_setup
    
    try:
        # Open both positions
        result1 = await client.open_position(
            symbol=setup.asset_1,
            side=setup.side_1,
            margin=setup.margin_1,
            leverage=setup.leverage_1
        )
        
        result2 = await client.open_position(
            symbol=setup.asset_2,
            side=setup.side_2,
            margin=setup.margin_2,
            leverage=setup.leverage_2
        )
        
        session.trade_setup.is_active = True
        session.is_monitoring = True
        
        side1_emoji = "📈" if setup.side_1 == "long" else "📉"
        side2_emoji = "📈" if setup.side_2 == "long" else "📉"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"""
✅ **Positions Opened Successfully!**

**Position 1:** {setup.asset_1} {side1_emoji} {setup.side_1.upper()}
**Position 2:** {setup.asset_2} {side2_emoji} {setup.side_2.upper()}

🎯 Profit Target: ${setup.profit_target:,.2f}
🔄 Monitoring started...

Use /status to check PnL
Use /panic for emergency close
Use /stop to stop monitoring
""",
            parse_mode='Markdown'
        )
        
        # Start monitoring task
        session.monitoring_task = asyncio.create_task(
            monitor_positions(user_id, context)
        )
        
    except Exception as e:
        logger.error(f"Failed to open positions: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Failed to open positions: {e}"
        )
    
    finally:
        await client.close()
    
    return ConversationHandler.END


async def monitor_positions(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Background task to monitor positions and profit target"""
    session = get_session(user_id)
    setup = session.trade_setup
    monitor_interval = int(os.getenv('MONITOR_INTERVAL', '5'))
    
    client = get_lighter_client()
    
    try:
        while session.is_monitoring:
            try:
                # Check if profit target is reached
                pnl_data = await client.get_total_pnl()
                current_pnl = pnl_data['unrealized_pnl']
                
                logger.info(f"User {user_id} - Current PnL: ${current_pnl:.2f} | Target: ${setup.profit_target:.2f}")
                
                if current_pnl >= setup.profit_target:
                    # Close all positions
                    close_results = await client.close_all_positions()
                    
                    total_pnl = sum(r.get('pnl', 0) for r in close_results if r.get('success'))
                    session.total_profit_booked += total_pnl
                    session.trades_completed += 1
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"""
🎉 **PROFIT TARGET REACHED!**

💰 Profit Booked: **${total_pnl:,.2f}**
📊 Total Profits: **${session.total_profit_booked:,.2f}**
🔢 Trades Completed: **{session.trades_completed}**

🔄 Reopening positions in 5 seconds...
""",
                        parse_mode='Markdown'
                    )
                    
                    await asyncio.sleep(5)
                    
                    if session.is_monitoring and setup.loop_enabled:
                        # Reopen positions
                        await client.open_position(
                            symbol=setup.asset_1,
                            side=setup.side_1,
                            margin=setup.margin_1,
                            leverage=setup.leverage_1
                        )
                        
                        await client.open_position(
                            symbol=setup.asset_2,
                            side=setup.side_2,
                            margin=setup.margin_2,
                            leverage=setup.leverage_2
                        )
                        
                        side1_emoji = "📈" if setup.side_1 == "long" else "📉"
                        side2_emoji = "📈" if setup.side_2 == "long" else "📉"
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"""
✅ **Positions Reopened!**

**Position 1:** {setup.asset_1} {side1_emoji} {setup.side_1.upper()}
**Position 2:** {setup.asset_2} {side2_emoji} {setup.side_2.upper()}

🎯 Profit Target: ${setup.profit_target:,.2f}
🔄 Monitoring resumed...
""",
                            parse_mode='Markdown'
                        )
                
                await asyncio.sleep(monitor_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error for user {user_id}: {e}")
                await asyncio.sleep(monitor_interval)
    
    finally:
        await client.close()
        logger.info(f"Monitoring stopped for user {user_id}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check current PnL and position status"""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
    
    session = get_session(user_id)
    client = get_lighter_client()
    
    try:
        positions = await client.get_positions()
        pnl_data = await client.get_total_pnl()
        balance = await client.get_balance()
        
        if not positions:
            status_text = f"""
📊 **Account Status**

💳 Balance: ${balance:,.2f}
📈 Open Positions: 0
💰 Session Profit: ${session.total_profit_booked:,.2f}
🔢 Trades Completed: {session.trades_completed}
🔄 Monitoring: {'✅ Active' if session.is_monitoring else '❌ Inactive'}
"""
        else:
            positions_text = ""
            for pos in positions:
                side_emoji = "📈" if pos.side == "long" else "📉"
                pnl_emoji = "🟢" if pos.unrealized_pnl >= 0 else "🔴"
                
                positions_text += f"""
**{pos.symbol}** {side_emoji} {pos.side.upper()}
• Entry: ${pos.entry_price:,.2f}
• Mark: ${pos.mark_price:,.2f}
• Size: {pos.size:.6f}
• Margin: ${pos.margin:,.2f}
• Leverage: {pos.leverage}x
• PnL: {pnl_emoji} ${pos.unrealized_pnl:,.2f} ({pos.pnl_percentage:+.2f}%)
"""
            
            status_text = f"""
📊 **Account Status**

💳 Balance: ${balance:,.2f}
📈 Open Positions: {len(positions)}
{positions_text}
━━━━━━━━━━━━━━━━━━━━━━

💰 **Total Unrealized PnL:** ${pnl_data['unrealized_pnl']:,.2f}
🎯 **Profit Target:** ${session.trade_setup.profit_target:,.2f}
💵 **Session Profit:** ${session.total_profit_booked:,.2f}
🔢 **Trades Completed:** {session.trades_completed}
🔄 **Monitoring:** {'✅ Active' if session.is_monitoring else '❌ Inactive'}
"""
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching status: {e}")
    
    finally:
        await client.close()


async def panic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Emergency close all positions"""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
    
    session = get_session(user_id)
    
    await update.message.reply_text("🚨 **PANIC SELL INITIATED**\n\nClosing all positions...", parse_mode='Markdown')
    
    # Stop monitoring
    session.is_monitoring = False
    if session.monitoring_task:
        session.monitoring_task.cancel()
        session.monitoring_task = None
    
    client = get_lighter_client()
    
    try:
        # Get current PnL before closing
        pnl_before = await client.get_total_pnl()
        
        # Close all positions
        results = await client.close_all_positions()
        
        total_pnl = sum(r.get('pnl', 0) for r in results if r.get('success'))
        successful = sum(1 for r in results if r.get('success'))
        failed = sum(1 for r in results if not r.get('success'))
        
        session.total_profit_booked += total_pnl
        session.trade_setup.is_active = False
        
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        
        result_text = f"""
🚨 **PANIC SELL COMPLETE**

{pnl_emoji} **Realized PnL:** ${total_pnl:,.2f}
✅ Positions Closed: {successful}
❌ Failed: {failed}

💵 **Total Session Profit:** ${session.total_profit_booked:,.2f}
🔢 **Trades Completed:** {session.trades_completed}

Use /trade to start a new setup.
"""
        
        await update.message.reply_text(result_text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error during panic sell: {e}")
    
    finally:
        await client.close()


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop monitoring without closing positions"""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
    
    session = get_session(user_id)
    
    if not session.is_monitoring:
        await update.message.reply_text("ℹ️ Monitoring is not active.")
        return
    
    # Stop monitoring
    session.is_monitoring = False
    if session.monitoring_task:
        session.monitoring_task.cancel()
        session.monitoring_task = None
    
    await update.message.reply_text(
        """
⏹️ **Monitoring Stopped**

Your positions are still open but not being monitored.

Commands:
• /status - Check current PnL
• /panic - Close all positions
• /trade - Start new trade setup
""",
        parse_mode='Markdown'
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current conversation"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Trade setup cancelled.")
    else:
        await update.message.reply_text("❌ Trade setup cancelled.")
    
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    help_text = """
🤖 **Lighter.xyz Futures Trading Bot**

This bot helps you execute paired futures trades with automatic profit booking.

**Commands:**
• /start - Start the bot
• /trade - Set up a new paired trade
• /status - Check current positions and PnL
• /panic - Emergency market sell all positions
• /stop - Stop monitoring (keeps positions open)
• /help - Show this help message

**How it works:**
1. Select first asset (BTC/ETH/SOL)
2. Choose LONG or SHORT
3. Enter margin amount
4. Set leverage
5. Repeat for second asset
6. Set profit target

The bot will:
- Open both positions simultaneously
- Monitor until profit target is reached
- Close positions and notify you
- Automatically reopen with same setup

**Tips:**
- Use opposite positions for hedging
- Set realistic profit targets
- Monitor /status regularly
- Use /panic for emergencies
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def set_commands(application):
    """Set bot commands for menu"""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("trade", "Set up a new paired trade"),
        BotCommand("status", "Check current positions and PnL"),
        BotCommand("panic", "Emergency close all positions"),
        BotCommand("stop", "Stop monitoring"),
        BotCommand("help", "Show help message"),
    ]
    await application.bot.set_my_commands(commands)


def main():
    """Start the bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token or token == 'your_telegram_bot_token_here':
        logger.error("TELEGRAM_BOT_TOKEN not set in environment variables!")
        print("\n❌ Error: Please set TELEGRAM_BOT_TOKEN in your .env file")
        print("1. Copy .env.example to .env")
        print("2. Add your Telegram bot token from @BotFather")
        return
    
    # Build application
    application = Application.builder().token(token).build()
    
    # Create conversation handler for trade setup
    trade_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('trade', trade_command),
        ],
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
        fallbacks=[
            CallbackQueryHandler(cancel, pattern='^cancel$'),
            CommandHandler('cancel', lambda u, c: cancel(u, c)),
        ],
    )
    
    # Add handlers
    application.add_handler(trade_handler)
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('panic', panic_command))
    application.add_handler(CommandHandler('stop', stop_command))
    application.add_handler(CommandHandler('help', help_command))
    
    # Set up commands menu
    application.post_init = set_commands
    
    # Start the bot
    logger.info("Starting Lighter.xyz Futures Trading Bot...")
    print("\n🤖 Lighter.xyz Futures Trading Bot Started!")
    print("Press Ctrl+C to stop\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
