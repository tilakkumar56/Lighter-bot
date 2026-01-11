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
    """Create and return a Lighter client instance"""
    api_key = os.getenv('LIGHTER_API_KEY', '')
    api_secret = os.getenv('LIGHTER_API_SECRET', '')
    wallet_address = os.getenv('LIGHTER_WALLET_ADDRESS', '')
    base_url = os.getenv('LIGHTER_API_URL', 'https://api.lighter.xyz')
    
    # Check if all credentials are properly configured
    placeholder_values = ['', 'your_lighter_api_key_here', 'your_lighter_api_secret_here', 'your_wallet_address_here']
    
    use_mock = (
        not api_key or 
        not api_secret or 
        not wallet_address or
        api_key.lower() in placeholder_values or
        api_secret.lower() in placeholder_values or
        wallet_address.lower() in placeholder_values or
        'your_' in api_key.lower() or
        'your_' in api_secret.lower() or
        'your_' in wallet_address.lower()
    )
    
    if use_mock:
        logger.info("=" * 50)
        logger.info("MOCK MODE - Using simulated trading")
        logger.info("=" * 50)
        return MockLighterClient(api_key, api_secret, wallet_address, base_url)
    
    logger.info("LIVE MODE - Using real Lighter.xyz API")
    return LighterClient(api_key, api_secret, wallet_address, base_url)


def is_user_authorized(user_id: int) -> bool:
    allowed_ids = os.getenv('ALLOWED_USER_IDS', '')
    if not allowed_ids or allowed_ids == 'your_telegram_user_id':
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
    
    get_session(user_id)
    welcome_text = """🤖 *Lighter.xyz Futures Trading Bot*

⚠️ *MOCK MODE ACTIVE* - No real trades!

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

⚠️ *MOCK MODE* - Simulated trading

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
    
    await query.edit_message_text("⏳ Opening positions... (MOCK MODE)")
    client = get_lighter_client()
    setup = session.trade_setup
    
    try:
        await client.open_position(setup.asset_1, setup.side_1, setup.margin_1, setup.leverage_1)
        await client.open_position(setup.asset_2, setup.side_2, setup.margin_2, setup.leverage_2)
        
        session.trade_setup.is_active = True
        session.is_monitoring = True
        e1 = "📈" if setup.side_1 == "long" else "📉"
        e2 = "📈" if setup.side_2 == "long" else "📉"
        
        await context.bot.send_message(chat_id=user_id, text=f"""✅ *Positions Opened!* (MOCK MODE)

*Position 1:* {setup.asset_1} {e1} {setup.side_1.upper()}
*Position 2:* {setup.asset_2} {e2} {setup.side_2.upper()}

🎯 Profit Target: ${setup.profit_target:,.2f}
🔄 Monitoring started...

📊 Use /status to check PnL
🚨 Use /panic for emergency close
⏹️ Use /stop to stop monitoring

_Check your terminal for live updates!_""", parse_mode='Markdown')
        
        session.monitoring_task = asyncio.create_task(monitor_positions(user_id, context))
    except Exception as e:
        logger.error(f"Failed to open positions: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"❌ Failed to open positions: {e}")
    finally:
        await client.close()
    
    return ConversationHandler.END


async def monitor_positions(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    session = get_session(user_id)
    setup = session.trade_setup
    interval = int(os.getenv('MONITOR_INTERVAL', '5'))
    client = get_lighter_client()
    
    logger.info("=" * 50)
    logger.info(f"MONITORING STARTED for user {user_id}")
    logger.info(f"Profit Target: ${setup.profit_target:,.2f}")
    logger.info(f"Check interval: {interval} seconds")
    logger.info("=" * 50)
    
    try:
        check_count = 0
        while session.is_monitoring:
            try:
                check_count += 1
                pnl_data = await client.get_total_pnl()
                current_pnl = pnl_data['unrealized_pnl']
                
                # Log every check to terminal
                pnl_emoji = "🟢" if current_pnl >= 0 else "🔴"
                logger.info(f"[Check #{check_count}] PnL: {pnl_emoji} ${current_pnl:,.2f} | Target: ${setup.profit_target:,.2f} | {'TARGET REACHED!' if current_pnl >= setup.profit_target else 'Waiting...'}")
                
                if current_pnl >= setup.profit_target:
                    logger.info("=" * 50)
                    logger.info("🎉 PROFIT TARGET REACHED! Closing positions...")
                    logger.info("=" * 50)
                    
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
                        logger.info("Reopening positions...")
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
                logger.info("Monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(interval)
    finally:
        await client.close()
        logger.info(f"Monitoring stopped for user {user_id}")


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
        
        if not positions:
            text = f"""📊 *Account Status* (MOCK)

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
            
            text = f"""📊 *Account Status* (MOCK)

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
    finally:
        await client.close()


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
    finally:
        await client.close()


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
    await update.message.reply_text("""🤖 *Lighter.xyz Futures Bot*

*Commands:*
• /start - Start bot
• /trade - New paired trade
• /status - Check PnL
• /panic - Emergency close
• /stop - Stop monitoring
• /help - This message

⚠️ Currently in MOCK MODE
No real trades are being made.""", parse_mode='Markdown')


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
    if not token or token == 'your_telegram_bot_token_here':
        print("\n❌ Set TELEGRAM_BOT_TOKEN in .env file")
        return
    
    print("\n" + "=" * 50)
    print("🤖 LIGHTER.XYZ FUTURES TRADING BOT")
    print("=" * 50)
    print("Mode: MOCK (Simulated Trading)")
    print("No real money will be used!")
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
    
    logger.info("Starting Lighter.xyz Futures Trading Bot...")
    print("Press Ctrl+C to stop\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
