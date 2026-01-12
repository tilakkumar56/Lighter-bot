"""
Lighter.xyz Futures Trading Telegram Bot
Using Official Lighter SDK for Real Trading
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


def get_session(user_id: int) -> UserSession:
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()
    return user_sessions[user_id]


# Global client instance (reused for efficiency)
_lighter_client = None


def get_lighter_client():
    """Create and return a Lighter client instance"""
    global _lighter_client
    
    use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
    
    if use_mock:
        logger.info("Using MOCK client")
        return MockLighterClient()
    
    # Check for required credentials
    # Use LIGHTER_PRIVATE_KEY (80 chars from website) or fallback to ETH_PRIVATE_KEY
    private_key = os.getenv('LIGHTER_PRIVATE_KEY', '') or os.getenv('ETH_PRIVATE_KEY', '')
    account_index = os.getenv('ACCOUNT_INDEX', '')
    api_key_index = int(os.getenv('API_KEY_INDEX', '10'))
    base_url = os.getenv('LIGHTER_BASE_URL', 'https://mainnet.zklighter.elliot.ai')
    
    if not private_key or not account_index:
        logger.warning("Missing credentials, using MOCK client")
        return MockLighterClient()
    
    if _lighter_client is None:
        try:
            _lighter_client = LighterClient(
                base_url=base_url,
                private_key=private_key,
                account_index=int(account_index),
                api_key_index=api_key_index
            )
            logger.info("LIVE MODE - Connected to Lighter.xyz")
        except Exception as e:
            logger.error(f"Failed to create client: {e}")
            logger.warning("Falling back to MOCK client")
            return MockLighterClient()
    
    return _lighter_client


def is_user_authorized(user_id: int) -> bool:
    allowed_ids = os.getenv('ALLOWED_USER_IDS', '')
    if not allowed_ids:
        return True
    allowed_list = [int(uid.strip()) for uid in allowed_ids.split(',') if uid.strip()]
    return user_id in allowed_list


def get_asset_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("₿ BTC", callback_data="asset_BTC"),
         InlineKeyboardButton("Ξ ETH", callback_data="asset_ETH"),
         InlineKeyboardButton("◎ SOL", callback_data="asset_SOL")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_side_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📈 LONG", callback_data="side_long"),
         InlineKeyboardButton("📉 SHORT", callback_data="side_short")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[
        InlineKeyboardButton("✅ Confirm & Start", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ Cancel", callback_data="confirm_no")
    ]]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return ConversationHandler.END
    
    use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
    mode = "⚠️ MOCK MODE" if use_mock else "🔴 LIVE TRADING"
    
    get_session(user_id)
    welcome_text = f"""🤖 *Lighter.xyz Futures Trading Bot*

{mode}

*Commands:*
• /trade - Start new paired trade
• /status - Check current PnL
• /panic - Close all positions
• /stop - Stop monitoring

Select *Asset 1* to begin:"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=get_asset_keyboard())
    return SELECT_ASSET_1


async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return ConversationHandler.END
    
    session = get_session(user_id)
    if session.is_monitoring:
        await update.message.reply_text("⚠️ A trade is already active. Use /stop first or /panic to close all.")
        return ConversationHandler.END
    
    session.trade_setup = TradeSetup()
    await update.message.reply_text("🔄 *New Paired Trade Setup*\n\nStep 1/9: Select *Asset 1*:",
                                     parse_mode='Markdown', reply_markup=get_asset_keyboard())
    return SELECT_ASSET_1


async def select_asset_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    asset = query.data.replace("asset_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.asset_1 = asset
    
    await query.edit_message_text(f"✅ Asset 1: *{asset}*\n\nStep 2/9: LONG or SHORT on {asset}?",
                                   parse_mode='Markdown', reply_markup=get_side_keyboard())
    return SELECT_SIDE_1


async def select_side_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    side = query.data.replace("side_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.side_1 = side
    emoji = "📈" if side == "long" else "📉"
    
    await query.edit_message_text(
        f"✅ Asset 1: *{session.trade_setup.asset_1}* {emoji} {side.upper()}\n\n"
        f"Step 3/9: Enter *margin amount* in USD:\n(Example: 100)", parse_mode='Markdown')
    return ENTER_MARGIN_1


async def enter_margin_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        margin = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if margin <= 0:
            raise ValueError()
        session.trade_setup.margin_1 = margin
        emoji = "📈" if session.trade_setup.side_1 == "long" else "📉"
        
        await update.message.reply_text(
            f"✅ Asset 1: *{session.trade_setup.asset_1}* {emoji} {session.trade_setup.side_1.upper()}\n"
            f"✅ Margin 1: *${margin:,.2f}*\n\nStep 4/9: Enter *leverage* (1-100):", parse_mode='Markdown')
        return ENTER_LEVERAGE_1
    except:
        await update.message.reply_text("❌ Invalid amount. Enter a valid number:")
        return ENTER_MARGIN_1


async def enter_leverage_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        leverage = int(update.message.text.strip().replace('x', '').replace('X', ''))
        if leverage < 1 or leverage > 100:
            raise ValueError()
        session.trade_setup.leverage_1 = leverage
        setup = session.trade_setup
        emoji = "📈" if setup.side_1 == "long" else "📉"
        
        await update.message.reply_text(
            f"✅ *Position 1 Complete!*\n"
            f"   Asset: {setup.asset_1}\n"
            f"   Side: {emoji} {setup.side_1.upper()}\n"
            f"   Margin: ${setup.margin_1:,.2f}\n"
            f"   Leverage: {leverage}x\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Step 5/9: Select *Asset 2*:",
            parse_mode='Markdown', reply_markup=get_asset_keyboard())
        return SELECT_ASSET_2
    except:
        await update.message.reply_text("❌ Invalid leverage. Enter 1-100:")
        return ENTER_LEVERAGE_1


async def select_asset_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    asset = query.data.replace("asset_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.asset_2 = asset
    
    await query.edit_message_text(f"✅ Asset 2: *{asset}*\n\nStep 6/9: LONG or SHORT on {asset}?",
                                   parse_mode='Markdown', reply_markup=get_side_keyboard())
    return SELECT_SIDE_2


async def select_side_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    side = query.data.replace("side_", "")
    session = get_session(update.effective_user.id)
    session.trade_setup.side_2 = side
    emoji = "📈" if side == "long" else "📉"
    
    await query.edit_message_text(
        f"✅ Asset 2: *{session.trade_setup.asset_2}* {emoji} {side.upper()}\n\n"
        f"Step 7/9: Enter *margin amount* in USD:\n(Example: 100)", parse_mode='Markdown')
    return ENTER_MARGIN_2


async def enter_margin_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        margin = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if margin <= 0:
            raise ValueError()
        session.trade_setup.margin_2 = margin
        emoji = "📈" if session.trade_setup.side_2 == "long" else "📉"
        
        await update.message.reply_text(
            f"✅ Asset 2: *{session.trade_setup.asset_2}* {emoji} {session.trade_setup.side_2.upper()}\n"
            f"✅ Margin 2: *${margin:,.2f}*\n\nStep 8/9: Enter *leverage* (1-100):", parse_mode='Markdown')
        return ENTER_LEVERAGE_2
    except:
        await update.message.reply_text("❌ Invalid amount. Enter a valid number:")
        return ENTER_MARGIN_2


async def enter_leverage_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        leverage = int(update.message.text.strip().replace('x', '').replace('X', ''))
        if leverage < 1 or leverage > 100:
            raise ValueError()
        session.trade_setup.leverage_2 = leverage
        setup = session.trade_setup
        emoji = "📈" if setup.side_2 == "long" else "📉"
        
        await update.message.reply_text(
            f"✅ *Position 2 Complete!*\n"
            f"   Asset: {setup.asset_2}\n"
            f"   Side: {emoji} {setup.side_2.upper()}\n"
            f"   Margin: ${setup.margin_2:,.2f}\n"
            f"   Leverage: {leverage}x\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Step 9/9: Enter *profit target* in USD:\n(Example: 10)", parse_mode='Markdown')
        return ENTER_PROFIT_TARGET
    except:
        await update.message.reply_text("❌ Invalid leverage. Enter 1-100:")
        return ENTER_LEVERAGE_2


async def enter_profit_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = get_session(update.effective_user.id)
    try:
        target = float(update.message.text.strip().replace('$', '').replace(',', ''))
        if target <= 0:
            raise ValueError()
        session.trade_setup.profit_target = target
        setup = session.trade_setup
        e1 = "📈" if setup.side_1 == "long" else "📉"
        e2 = "📈" if setup.side_2 == "long" else "📉"
        total_margin = setup.margin_1 + setup.margin_2
        
        use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
        mode = "⚠️ MOCK MODE" if use_mock else "🔴 LIVE TRADING"
        
        summary = f"""📋 *Trade Setup Summary*

*Position 1:*
• Asset: {setup.asset_1}
• Side: {e1} {setup.side_1.upper()}
• Margin: ${setup.margin_1:,.2f}
• Leverage: {setup.leverage_1}x

*Position 2:*
• Asset: {setup.asset_2}
• Side: {e2} {setup.side_2.upper()}
• Margin: ${setup.margin_2:,.2f}
• Leverage: {setup.leverage_2}x

━━━━━━━━━━━━━━━━━━━━━━
💰 *Total Margin:* ${total_margin:,.2f}
🎯 *Profit Target:* ${target:,.2f}
🔄 *Auto-Reopen:* Enabled

{mode}

Confirm to open both positions?"""
        await update.message.reply_text(summary, parse_mode='Markdown', reply_markup=get_confirm_keyboard())
        return CONFIRM_TRADE
    except:
        await update.message.reply_text("❌ Invalid amount. Enter a valid number:")
        return ENTER_PROFIT_TARGET


async def confirm_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    if query.data == "confirm_no":
        await query.edit_message_text("❌ Trade setup cancelled.")
        return ConversationHandler.END
    
    await query.edit_message_text("⏳ Opening positions on Lighter.xyz...")
    client = get_lighter_client()
    setup = session.trade_setup
    
    try:
        # Open first position
        logger.info(f"Opening position 1: {setup.asset_1} {setup.side_1}")
        await client.open_position(setup.asset_1, setup.side_1, setup.margin_1, setup.leverage_1)
        
        # Open second position
        logger.info(f"Opening position 2: {setup.asset_2} {setup.side_2}")
        await client.open_position(setup.asset_2, setup.side_2, setup.margin_2, setup.leverage_2)
        
        session.trade_setup.is_active = True
        session.is_monitoring = True
        e1 = "📈" if setup.side_1 == "long" else "📉"
        e2 = "📈" if setup.side_2 == "long" else "📉"
        
        await context.bot.send_message(chat_id=user_id, text=f"""✅ *Positions Opened Successfully!*

*Position 1:* {setup.asset_1} {e1} {setup.side_1.upper()}
*Position 2:* {setup.asset_2} {e2} {setup.side_2.upper()}

🎯 Profit Target: ${setup.profit_target:,.2f}
🔄 Monitoring started...

📊 Use /status to check PnL
🚨 Use /panic for emergency close
⏹️ Use /stop to stop monitoring""", parse_mode='Markdown')
        
        session.monitoring_task = asyncio.create_task(monitor_positions(user_id, context))
        
    except Exception as e:
        logger.error(f"Failed to open positions: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"❌ Failed to open positions:\n\n{e}")
    
    return ConversationHandler.END


async def monitor_positions(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(user_id)
    setup = session.trade_setup
    interval = int(os.getenv('MONITOR_INTERVAL', '5'))
    client = get_lighter_client()
    
    logger.info(f"Monitoring started | Target: ${setup.profit_target}")
    
    try:
        check_count = 0
        while session.is_monitoring:
            try:
                check_count += 1
                pnl_data = await client.get_total_pnl()
                current_pnl = pnl_data['unrealized_pnl']
                
                pnl_emoji = "🟢" if current_pnl >= 0 else "🔴"
                logger.info(f"[#{check_count}] PnL: {pnl_emoji} ${current_pnl:,.2f} | Target: ${setup.profit_target:,.2f}")
                
                if current_pnl >= setup.profit_target:
                    logger.info("🎉 PROFIT TARGET REACHED!")
                    
                    results = await client.close_all_positions()
                    total_pnl = sum(r.get('pnl', 0) for r in results if r.get('success'))
                    session.total_profit_booked += total_pnl
                    session.trades_completed += 1
                    
                    await context.bot.send_message(chat_id=user_id, text=f"""🎉 *PROFIT TARGET REACHED!*

💰 Profit Booked: *${total_pnl:,.2f}*
📊 Total Profits: *${session.total_profit_booked:,.2f}*
🔢 Trades Completed: *{session.trades_completed}*

🔄 Reopening positions in 5 seconds...""", parse_mode='Markdown')
                    
                    await asyncio.sleep(5)
                    
                    if session.is_monitoring and setup.loop_enabled:
                        await client.open_position(setup.asset_1, setup.side_1, setup.margin_1, setup.leverage_1)
                        await client.open_position(setup.asset_2, setup.side_2, setup.margin_2, setup.leverage_2)
                        e1 = "📈" if setup.side_1 == "long" else "📉"
                        e2 = "📈" if setup.side_2 == "long" else "📉"
                        
                        await context.bot.send_message(chat_id=user_id, text=f"""✅ *Positions Reopened!*

*Position 1:* {setup.asset_1} {e1} {setup.side_1.upper()}
*Position 2:* {setup.asset_2} {e2} {setup.side_2.upper()}

🎯 Profit Target: ${setup.profit_target:,.2f}
🔄 Monitoring resumed...""", parse_mode='Markdown')
                        check_count = 0
                
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
        await update.message.reply_text("❌ Not authorized.")
        return
    
    session = get_session(user_id)
    client = get_lighter_client()
    
    try:
        positions = await client.get_positions()
        pnl_data = await client.get_total_pnl()
        balance = await client.get_balance()
        
        use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
        mode = "(MOCK)" if use_mock else "(LIVE)"
        
        if not positions:
            text = f"""📊 *Account Status* {mode}

💳 Balance: ${balance:,.2f}
📈 Open Positions: 0
💰 Session Profit: ${session.total_profit_booked:,.2f}
🔢 Trades Completed: {session.trades_completed}
🔄 Monitoring: {'✅ Active' if session.is_monitoring else '❌ Inactive'}"""
        else:
            pos_text = ""
            for pos in positions:
                se = "📈" if pos.side == "long" else "📉"
                pe = "🟢" if pos.unrealized_pnl >= 0 else "🔴"
                pos_text += f"\n*{pos.symbol}* {se} {pos.side.upper()}\n"
                pos_text += f"• Entry: ${pos.entry_price:,.2f}\n"
                pos_text += f"• Mark: ${pos.mark_price:,.2f}\n"
                pos_text += f"• PnL: {pe} ${pos.unrealized_pnl:,.2f} ({pos.pnl_percentage:+.2f}%)\n"
            
            text = f"""📊 *Account Status* {mode}

💳 Balance: ${balance:,.2f}
{pos_text}
━━━━━━━━━━━━━━━━━━━━━━
💰 *Total PnL:* ${pnl_data['unrealized_pnl']:,.2f}
🎯 *Target:* ${session.trade_setup.profit_target:,.2f}
💵 *Session Profit:* ${session.total_profit_booked:,.2f}
🔄 *Monitoring:* {'✅ Active' if session.is_monitoring else '❌ Inactive'}"""
        
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def panic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ Not authorized.")
        return
    
    session = get_session(user_id)
    await update.message.reply_text("🚨 *PANIC SELL* - Closing all positions...", parse_mode='Markdown')
    
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
        emoji = "🟢" if total_pnl >= 0 else "🔴"
        
        await update.message.reply_text(f"""🚨 *PANIC SELL COMPLETE*

{emoji} *Realized PnL:* ${total_pnl:,.2f}
💵 *Total Session Profit:* ${session.total_profit_booked:,.2f}

Use /trade to start new setup.""", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_authorized(user_id):
        await update.message.reply_text("❌ Not authorized.")
        return
    
    session = get_session(user_id)
    if not session.is_monitoring:
        await update.message.reply_text("ℹ️ Monitoring not active.")
        return
    
    session.is_monitoring = False
    if session.monitoring_task:
        session.monitoring_task.cancel()
        session.monitoring_task = None
    
    await update.message.reply_text("""⏹️ *Monitoring Stopped*

Positions still open.

/status - Check PnL
/panic - Close all
/trade - New setup""", parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
    mode = "⚠️ MOCK MODE" if use_mock else "🔴 LIVE TRADING"
    
    await update.message.reply_text(f"""🤖 *Lighter.xyz Futures Bot*

*Commands:*
• /start - Start bot
• /trade - New paired trade
• /status - Check PnL
• /panic - Emergency close
• /stop - Stop monitoring
• /help - This message

{mode}""", parse_mode='Markdown')


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Cancelled.")
    else:
        await update.message.reply_text("❌ Cancelled.")
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
    if not token:
        print("\n❌ Set TELEGRAM_BOT_TOKEN in .env file")
        return
    
    use_mock = os.getenv('USE_MOCK', 'false').lower() == 'true'
    mode = "MOCK (Simulated)" if use_mock else "LIVE (Real Trading)"
    
    print("\n" + "=" * 50)
    print("🤖 LIGHTER.XYZ FUTURES TRADING BOT")
    print("=" * 50)
    print(f"Mode: {mode}")
    if not use_mock:
        print("⚠️  REAL MONEY WILL BE USED!")
    print("=" * 50 + "\n")
    
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
