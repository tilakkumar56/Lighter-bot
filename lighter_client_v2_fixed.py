"""
Lighter.xyz API Client for Futures Trading
Using Official Lighter SDK - FIXED VERSION with Real PnL Fetching
"""
import os
import time
import logging
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import random

logger = logging.getLogger(__name__)

# Try to import lighter SDK
try:
    import lighter
    from lighter import ApiClient, Configuration, AccountApi, OrderApi, TransactionApi
    LIGHTER_SDK_AVAILABLE = True
except ImportError:
    LIGHTER_SDK_AVAILABLE = False
    logger.warning("Lighter SDK not installed. Run: pip install lighter-sdk")


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
    order_index: Optional[int] = None
    
    @property
    def pnl_percentage(self) -> float:
        if self.margin == 0:
            return 0.0
        return (self.unrealized_pnl / self.margin) * 100


class LighterClient:
    """
    Client for Lighter.xyz futures trading using official SDK
    """
    
    SUPPORTED_ASSETS = ['BTC', 'ETH', 'SOL']
    
    # Market IDs on Lighter (from order_books API)
    MARKET_IDS = {
        'BTC': 1,
        'ETH': 0,
        'SOL': 2,
    }
    
    # Reverse mapping: market_id -> symbol
    MARKET_SYMBOLS = {
        1: 'BTC',
        0: 'ETH',
        2: 'SOL',
    }
    
    # Size decimals for each market (from orderbook)
    SIZE_DECIMALS = {
        'BTC': 5,
        'ETH': 4,
        'SOL': 3,
    }
    
    # Price decimals for each market
    PRICE_DECIMALS = {
        'BTC': 1,
        'ETH': 2,
        'SOL': 3,
    }
    
    def __init__(
        self,
        base_url: str,
        private_key: str,
        account_index: int,
        api_key_index: int = 10
    ):
        self.base_url = base_url
        self.private_key = private_key
        self.account_index = account_index
        self.api_key_index = api_key_index
        
        self._signer_client = None
        self._api_client = None
        self._account_api = None
        self._order_api = None
        self._transaction_api = None
        self._local_positions: Dict[str, Position] = {}  # For tracking our trades
        self._order_counter = int(time.time())
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Lighter SDK clients"""
        if not LIGHTER_SDK_AVAILABLE:
            raise Exception("Lighter SDK not installed. Run: pip install lighter-sdk")
        
        try:
            pk = self.private_key.strip()
            if pk.startswith("0x"):
                pk = pk[2:]
            
            logger.info(f"Initializing Lighter client...")
            logger.info(f"  Base URL: {self.base_url}")
            logger.info(f"  Account Index: {self.account_index}")
            logger.info(f"  API Key Index: {self.api_key_index}")
            logger.info(f"  Private Key Length: {len(pk)} chars")
            
            self._signer_client = lighter.SignerClient(
                url=self.base_url,
                api_private_keys={self.api_key_index: pk},
                account_index=self.account_index
            )
            
            config = Configuration(host=self.base_url)
            self._api_client = ApiClient(config)
            self._account_api = AccountApi(self._api_client)
            self._order_api = OrderApi(self._api_client)
            self._transaction_api = TransactionApi(self._api_client)
            
            logger.info("=" * 50)
            logger.info("LIGHTER CLIENT INITIALIZED SUCCESSFULLY")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"Failed to initialize Lighter client: {e}")
            raise
    
    async def close(self):
        """Cleanup"""
        if self._api_client:
            await self._api_client.close()
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information including positions and PnL"""
        try:
            account = await self._account_api.account(self.account_index)
            
            result = {
                'index': getattr(account, 'index', self.account_index),
                'collateral': float(getattr(account, 'collateral', 0)),
                'positions': [],
                'total_unrealized_pnl': 0.0,
            }
            
            # Try to get positions from account data
            if hasattr(account, 'positions') and account.positions:
                logger.info(f"Found {len(account.positions)} positions in account")
                for pos_data in account.positions:
                    try:
                        market_id = getattr(pos_data, 'market_index', None) or getattr(pos_data, 'market_id', None)
                        symbol = self.MARKET_SYMBOLS.get(market_id, f"MARKET_{market_id}")
                        
                        # Get position details
                        size = float(getattr(pos_data, 'size', 0) or getattr(pos_data, 'base_amount', 0) or 0)
                        entry_price = float(getattr(pos_data, 'entry_price', 0) or getattr(pos_data, 'avg_entry_price', 0) or 0)
                        mark_price = float(getattr(pos_data, 'mark_price', 0) or 0)
                        unrealized_pnl = float(getattr(pos_data, 'unrealized_pnl', 0) or getattr(pos_data, 'pnl', 0) or 0)
                        margin = float(getattr(pos_data, 'margin', 0) or getattr(pos_data, 'collateral', 0) or 0)
                        leverage = int(getattr(pos_data, 'leverage', 1) or 1)
                        
                        # Determine side
                        side = 'long' if size > 0 else 'short'
                        size = abs(size)
                        
                        if size > 0:
                            result['positions'].append({
                                'symbol': symbol,
                                'side': side,
                                'size': size,
                                'entry_price': entry_price,
                                'mark_price': mark_price,
                                'unrealized_pnl': unrealized_pnl,
                                'margin': margin,
                                'leverage': leverage,
                            })
                            result['total_unrealized_pnl'] += unrealized_pnl
                            logger.info(f"  Position: {symbol} {side} size={size:.6f} pnl=${unrealized_pnl:.2f}")
                    except Exception as e:
                        logger.warning(f"Error parsing position: {e}")
            
            # Also check for unrealized_pnl at account level
            if hasattr(account, 'unrealized_pnl'):
                result['total_unrealized_pnl'] = float(account.unrealized_pnl)
                logger.info(f"Account unrealized PnL: ${result['total_unrealized_pnl']:.2f}")
            
            # Check for total_pnl or pnl field
            if hasattr(account, 'total_pnl'):
                result['total_unrealized_pnl'] = float(account.total_pnl)
            if hasattr(account, 'pnl'):
                result['total_unrealized_pnl'] = float(account.pnl)
            
            return result
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            import traceback
            traceback.print_exc()
            return {'index': self.account_index, 'collateral': 0, 'positions': [], 'total_unrealized_pnl': 0}
    
    async def get_balance(self) -> float:
        """Get available balance"""
        try:
            info = await self.get_account_info()
            return info.get('collateral', 0.0)
        except:
            return 0.0
    
    async def get_mark_price(self, symbol: str) -> float:
        """Get current mark price"""
        try:
            market_id = self.MARKET_IDS.get(symbol.upper(), 1)
            result = await self._order_api.order_book_details(market_id=market_id)
            
            if result and hasattr(result, 'order_book_details') and result.order_book_details:
                ob = result.order_book_details[0]
                if hasattr(ob, 'last_trade_price') and ob.last_trade_price:
                    price = float(ob.last_trade_price)
                    logger.info(f"Got price for {symbol}: ${price:,.2f}")
                    return price
            
            logger.warning(f"No price data found for {symbol}")
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get mark price for {symbol}: {e}")
            return 0.0
    
    async def get_positions(self) -> List[Position]:
        """Get all open positions - fetches from API and merges with local tracking"""
        positions = []
        
        # First, try to get real positions from API
        try:
            account_info = await self.get_account_info()
            api_positions = account_info.get('positions', [])
            
            for pos_data in api_positions:
                symbol = pos_data.get('symbol', '')
                if symbol:
                    pos = Position(
                        symbol=symbol,
                        side=pos_data.get('side', 'long'),
                        size=pos_data.get('size', 0),
                        entry_price=pos_data.get('entry_price', 0),
                        mark_price=pos_data.get('mark_price', 0),
                        leverage=pos_data.get('leverage', 1),
                        margin=pos_data.get('margin', 0),
                        unrealized_pnl=pos_data.get('unrealized_pnl', 0),
                        realized_pnl=0,
                        liquidation_price=0,
                    )
                    positions.append(pos)
                    
                    # Update local tracking
                    if symbol in self._local_positions:
                        self._local_positions[symbol].unrealized_pnl = pos.unrealized_pnl
                        self._local_positions[symbol].mark_price = pos.mark_price
            
            if positions:
                logger.info(f"Got {len(positions)} positions from API")
                return positions
        except Exception as e:
            logger.warning(f"Could not fetch positions from API: {e}")
        
        # Fallback: Update local positions with current prices
        for symbol, pos in self._local_positions.items():
            price = await self.get_mark_price(symbol)
            if price > 0:
                pos.mark_price = price
                diff = price - pos.entry_price
                if pos.side == 'short':
                    diff = -diff
                pos.unrealized_pnl = (diff / pos.entry_price) * pos.margin * pos.leverage
        
        return list(self._local_positions.values())
    
    async def get_total_pnl(self) -> Dict[str, float]:
        """Get total PnL - tries API first, then falls back to local calculation"""
        try:
            # Try to get real PnL from API
            account_info = await self.get_account_info()
            api_pnl = account_info.get('total_unrealized_pnl', None)
            api_positions = account_info.get('positions', [])
            
            # If we got PnL from API
            if api_pnl is not None and (api_pnl != 0 or len(api_positions) == 0):
                total_margin = sum(p.get('margin', 0) for p in api_positions)
                if total_margin == 0:
                    total_margin = sum(p.margin for p in self._local_positions.values())
                
                logger.info(f"API PnL: ${api_pnl:.2f} | Margin: ${total_margin:.2f}")
                
                return {
                    'unrealized_pnl': api_pnl,
                    'realized_pnl': 0,
                    'total_pnl': api_pnl,
                    'total_margin': total_margin,
                    'pnl_percentage': (api_pnl / total_margin * 100) if total_margin > 0 else 0
                }
        except Exception as e:
            logger.warning(f"Could not get PnL from API: {e}")
        
        # Fallback to local calculation
        positions = await self.get_positions()
        total_pnl = sum(p.unrealized_pnl for p in positions)
        total_margin = sum(p.margin for p in positions)
        
        logger.info(f"Local PnL: ${total_pnl:.2f} | Margin: ${total_margin:.2f}")
        
        return {
            'unrealized_pnl': total_pnl,
            'realized_pnl': 0,
            'total_pnl': total_pnl,
            'total_margin': total_margin,
            'pnl_percentage': (total_pnl / total_margin * 100) if total_margin > 0 else 0
        }
    
    async def open_position(self, symbol: str, side: str, margin: float, leverage: int) -> Dict[str, Any]:
        """Open a position using market order"""
        try:
            market_id = self.MARKET_IDS.get(symbol.upper(), 1)
            size_decimals = self.SIZE_DECIMALS.get(symbol.upper(), 5)
            price_decimals = self.PRICE_DECIMALS.get(symbol.upper(), 1)
            
            mark_price = await self.get_mark_price(symbol)
            
            if mark_price <= 0:
                raise Exception(f"Could not get valid price for {symbol}")
            
            # Set leverage
            margin_mode = 0  # Cross margin
            logger.info(f"Setting leverage to {leverage}x for {symbol}")
            try:
                await self._signer_client.update_leverage(market_id, margin_mode, leverage)
                logger.info(f"Leverage set successfully to {leverage}x")
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.warning(f"Could not set leverage: {e}")
                await asyncio.sleep(1.5)
            
            # Calculate size
            notional_value = margin * leverage
            size = notional_value / mark_price
            base_amount = int(size * (10 ** size_decimals))
            
            # is_ask: True = SELL (short), False = BUY (long)
            is_ask = side.lower() != 'long'
            
            # Add slippage
            if is_ask:
                price_with_slippage = mark_price * 0.98
            else:
                price_with_slippage = mark_price * 1.02
            
            price_int = int(price_with_slippage * (10 ** price_decimals))
            
            self._order_counter += 1
            client_order_index = self._order_counter
            
            logger.info(f"Opening {side} {symbol}:")
            logger.info(f"  Margin: ${margin:.2f}, Leverage: {leverage}x")
            logger.info(f"  Size: {size:.6f}, Price: ${mark_price:,.2f}")
            
            result = await self._signer_client.create_market_order(
                market_id,
                client_order_index,
                base_amount,
                price_int,
                is_ask,
                False  # reduce_only
            )
            
            # Track locally
            pos = Position(
                symbol=symbol.upper(),
                side=side.lower(),
                size=size,
                entry_price=mark_price,
                mark_price=mark_price,
                leverage=leverage,
                margin=margin,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                liquidation_price=mark_price * (0.5 if side == 'long' else 1.5),
                position_id=f"{symbol}_{client_order_index}",
                order_index=client_order_index
            )
            self._local_positions[symbol.upper()] = pos
            
            logger.info(f"Position opened: {result}")
            await asyncio.sleep(1.5)
            
            return {'success': True, 'order_index': client_order_index}
            
        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            await asyncio.sleep(1.5)
            raise
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close a position"""
        pos = self._local_positions.get(symbol.upper())
        if not pos:
            raise Exception(f"No position for {symbol}")
        
        try:
            market_id = self.MARKET_IDS.get(symbol.upper(), 1)
            size_decimals = self.SIZE_DECIMALS.get(symbol.upper(), 5)
            price_decimals = self.PRICE_DECIMALS.get(symbol.upper(), 1)
            
            mark_price = await self.get_mark_price(symbol)
            
            # Calculate PnL
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
                market_id,
                self._order_counter,
                base_amount,
                price_int,
                is_ask,
                True  # reduce_only
            )
            
            del self._local_positions[symbol.upper()]
            
            logger.info(f"Position closed: PnL=${pnl:,.2f}")
            return {'success': True, 'pnl': pnl}
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            raise
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all positions"""
        results = []
        for symbol in list(self._local_positions.keys()):
            try:
                r = await self.close_position(symbol)
                results.append({'symbol': symbol, 'success': True, 'pnl': r.get('pnl', 0)})
                await asyncio.sleep(1.5)
            except Exception as e:
                results.append({'symbol': symbol, 'success': False, 'error': str(e)})
        return results


class MockLighterClient:
    """Mock client for testing"""
    
    SUPPORTED_ASSETS = ['BTC', 'ETH', 'SOL']
    MARKET_INDICES = {'BTC': 0, 'ETH': 1, 'SOL': 2}
    
    def __init__(self, *args, **kwargs):
        self._positions: Dict[str, Position] = {}
        self._balance = 10000.0
        self._prices = {'BTC': 95000.0, 'ETH': 3200.0, 'SOL': 180.0}
        self._counter = int(time.time())
        
        logger.info("=" * 50)
        logger.info("MOCK MODE - No real trades")
        logger.info(f"Balance: ${self._balance:,.2f}")
        logger.info("=" * 50)
    
    async def close(self):
        pass
    
    async def get_balance(self) -> float:
        return self._balance
    
    async def get_mark_price(self, symbol: str) -> float:
        base = self._prices.get(symbol.upper(), 100.0)
        change = random.uniform(-0.005, 0.006)
        self._prices[symbol.upper()] = base * (1 + change)
        return self._prices[symbol.upper()]
    
    async def get_positions(self) -> List[Position]:
        for pos in self._positions.values():
            price = await self.get_mark_price(pos.symbol)
            pos.mark_price = price
            diff = price - pos.entry_price
            if pos.side == 'short':
                diff = -diff
            pos.unrealized_pnl = (diff / pos.entry_price) * pos.margin * pos.leverage
        return list(self._positions.values())
    
    async def open_position(self, symbol: str, side: str, margin: float, leverage: int) -> Dict[str, Any]:
        price = await self.get_mark_price(symbol)
        size = (margin * leverage) / price
        self._counter += 1
        
        pos = Position(
            symbol=symbol.upper(), side=side.lower(), size=size,
            entry_price=price, mark_price=price, leverage=leverage,
            margin=margin, unrealized_pnl=0, realized_pnl=0,
            liquidation_price=price * (0.5 if side == 'long' else 1.5),
            position_id=f"MOCK_{self._counter}"
        )
        self._positions[symbol.upper()] = pos
        self._balance -= margin
        
        logger.info(f"[MOCK] Opened {side} {symbol} @ ${price:,.2f}")
        return {'success': True, 'mock': True}
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        pos = self._positions.get(symbol.upper())
        if not pos:
            raise Exception(f"No position for {symbol}")
        
        price = await self.get_mark_price(symbol)
        diff = price - pos.entry_price
        if pos.side == 'short':
            diff = -diff
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
        return {
            'unrealized_pnl': total, 'realized_pnl': 0, 'total_pnl': total,
            'total_margin': margin,
            'pnl_percentage': (total / margin * 100) if margin > 0 else 0
        }
