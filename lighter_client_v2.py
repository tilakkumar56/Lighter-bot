"""
Lighter.xyz API Client for Futures Trading
Using Official Lighter SDK
"""
import os
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import random

logger = logging.getLogger(__name__)

# Try to import lighter SDK
try:
    import lighter
    LIGHTER_SDK_AVAILABLE = True
except ImportError:
    LIGHTER_SDK_AVAILABLE = False
    logger.warning("Lighter SDK not installed. Run: pip install lighter-sdk")


@dataclass
class Position:
    """Represents a trading position"""
    symbol: str
    side: str  # 'long' or 'short'
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
    
    # Market indices on Lighter (you may need to verify these)
    MARKET_INDICES = {
        'BTC': 0,  # BTC-USD market index
        'ETH': 1,  # ETH-USD market index
        'SOL': 2,  # SOL-USD market index
    }
    
    def __init__(
        self,
        base_url: str,
        eth_private_key: str,
        account_index: int,
        api_key_index: int = 10
    ):
        self.base_url = base_url
        self.eth_private_key = eth_private_key
        self.account_index = account_index
        self.api_key_index = api_key_index
        
        self._signer_client = None
        self._account_api = None
        self._order_api = None
        self._transaction_api = None
        self._positions: Dict[str, Position] = {}
        self._order_counter = int(time.time())  # For unique client_order_index
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Lighter SDK clients"""
        if not LIGHTER_SDK_AVAILABLE:
            raise Exception("Lighter SDK not installed. Run: pip install lighter-sdk")
        
        try:
            # Initialize SignerClient for transactions
            self._signer_client = lighter.SignerClient(
                url=self.base_url,
                api_private_keys={self.api_key_index: self.eth_private_key},
                account_index=self.account_index
            )
            
            # Initialize API clients
            self._account_api = lighter.AccountApi(self.base_url)
            self._order_api = lighter.OrderApi(self.base_url)
            self._transaction_api = lighter.TransactionApi(self.base_url)
            
            logger.info("=" * 50)
            logger.info("LIGHTER.XYZ CLIENT INITIALIZED")
            logger.info(f"  URL: {self.base_url}")
            logger.info(f"  Account Index: {self.account_index}")
            logger.info(f"  API Key Index: {self.api_key_index}")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"Failed to initialize Lighter client: {e}")
            raise
    
    async def close(self):
        """Cleanup (SDK handles connections internally)"""
        pass
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        try:
            account = self._account_api.account(index=self.account_index)
            return {
                'index': account.index,
                'l1_address': account.l1_address,
                'balance': float(account.collateral) if hasattr(account, 'collateral') else 0,
            }
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {}
    
    async def get_balance(self) -> float:
        """Get available balance in USD"""
        try:
            account = await self.get_account_info()
            return account.get('balance', 0.0)
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0
    
    async def get_mark_price(self, symbol: str) -> float:
        """Get current mark price for a symbol"""
        try:
            market_index = self.MARKET_INDICES.get(symbol.upper(), 0)
            orderbook = self._order_api.order_book_details(market_index=market_index)
            
            # Get mid price from orderbook
            if orderbook and hasattr(orderbook, 'best_ask') and hasattr(orderbook, 'best_bid'):
                best_ask = float(orderbook.best_ask) if orderbook.best_ask else 0
                best_bid = float(orderbook.best_bid) if orderbook.best_bid else 0
                if best_ask > 0 and best_bid > 0:
                    return (best_ask + best_bid) / 2
                return best_ask or best_bid
            
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get mark price for {symbol}: {e}")
            return 0.0
    
    async def get_positions(self) -> List[Position]:
        """Get all open positions"""
        return list(self._positions.values())
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol"""
        return self._positions.get(symbol.upper())
    
    async def open_position(
        self,
        symbol: str,
        side: str,  # 'long' or 'short'
        margin: float,
        leverage: int
    ) -> Dict[str, Any]:
        """
        Open a new futures position using market order
        """
        try:
            market_index = self.MARKET_INDICES.get(symbol.upper(), 0)
            mark_price = await self.get_mark_price(symbol)
            
            if mark_price <= 0:
                raise Exception(f"Could not get valid price for {symbol}")
            
            # Calculate position size
            notional_value = margin * leverage
            size = notional_value / mark_price
            
            # Convert to base amount (integer, check Lighter docs for decimals)
            # This may need adjustment based on Lighter's decimal precision
            base_amount = int(size * 1e8)  # Assuming 8 decimals
            
            # Price for market order (use a far price to ensure fill)
            if side.lower() == 'long':
                is_buy = True
                price = int(mark_price * 1.1 * 1e8)  # 10% above for buy
            else:
                is_buy = False
                price = int(mark_price * 0.9 * 1e8)  # 10% below for sell
            
            # Unique order index
            self._order_counter += 1
            client_order_index = self._order_counter
            
            logger.info("=" * 50)
            logger.info(f"OPENING {side.upper()} POSITION:")
            logger.info(f"  Symbol: {symbol}")
            logger.info(f"  Size: {size:.6f}")
            logger.info(f"  Price: ${mark_price:,.2f}")
            logger.info(f"  Margin: ${margin:,.2f}")
            logger.info(f"  Leverage: {leverage}x")
            logger.info("=" * 50)
            
            # Create market order using SignerClient
            result = self._signer_client.create_market_order(
                market_index=market_index,
                base_amount=base_amount,
                is_buy=is_buy,
                client_order_index=client_order_index
            )
            
            # Track position locally
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
            self._positions[symbol.upper()] = pos
            
            logger.info(f"Position opened successfully: {result}")
            
            return {'success': True, 'order_index': client_order_index, 'result': result}
            
        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            raise
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close an existing position with market order"""
        try:
            position = self._positions.get(symbol.upper())
            if not position:
                raise Exception(f"No open position found for {symbol}")
            
            market_index = self.MARKET_INDICES.get(symbol.upper(), 0)
            mark_price = await self.get_mark_price(symbol)
            
            # Calculate final PnL
            price_diff = mark_price - position.entry_price
            if position.side == 'short':
                price_diff = -price_diff
            pnl = (price_diff / position.entry_price) * position.margin * position.leverage
            
            # Close by placing opposite order
            base_amount = int(position.size * 1e8)
            is_buy = position.side == 'short'  # Opposite of position side
            
            if is_buy:
                price = int(mark_price * 1.1 * 1e8)
            else:
                price = int(mark_price * 0.9 * 1e8)
            
            self._order_counter += 1
            client_order_index = self._order_counter
            
            logger.info("=" * 50)
            logger.info(f"CLOSING POSITION:")
            logger.info(f"  Symbol: {symbol}")
            logger.info(f"  Side: {position.side.upper()}")
            logger.info(f"  Entry: ${position.entry_price:,.2f}")
            logger.info(f"  Exit: ${mark_price:,.2f}")
            logger.info(f"  PnL: ${pnl:,.2f}")
            logger.info("=" * 50)
            
            result = self._signer_client.create_market_order(
                market_index=market_index,
                base_amount=base_amount,
                is_buy=is_buy,
                client_order_index=client_order_index
            )
            
            # Remove from tracked positions
            del self._positions[symbol.upper()]
            
            return {'success': True, 'pnl': pnl, 'result': result}
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            raise
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all open positions"""
        results = []
        symbols = list(self._positions.keys())
        
        for symbol in symbols:
            try:
                result = await self.close_position(symbol)
                results.append({
                    'symbol': symbol,
                    'success': True,
                    'pnl': result.get('pnl', 0)
                })
            except Exception as e:
                results.append({
                    'symbol': symbol,
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    async def get_total_pnl(self) -> Dict[str, float]:
        """Get total PnL across all positions"""
        total_unrealized = 0.0
        total_margin = 0.0
        
        for symbol, pos in self._positions.items():
            # Update mark price
            current_price = await self.get_mark_price(symbol)
            if current_price > 0:
                pos.mark_price = current_price
                
                price_diff = current_price - pos.entry_price
                if pos.side == 'short':
                    price_diff = -price_diff
                
                pos.unrealized_pnl = (price_diff / pos.entry_price) * pos.margin * pos.leverage
            
            total_unrealized += pos.unrealized_pnl
            total_margin += pos.margin
        
        return {
            'unrealized_pnl': total_unrealized,
            'realized_pnl': 0.0,
            'total_pnl': total_unrealized,
            'total_margin': total_margin,
            'pnl_percentage': (total_unrealized / total_margin * 100) if total_margin > 0 else 0
        }


class MockLighterClient(LighterClient):
    """Mock client for testing without real API"""
    
    def __init__(self, *args, **kwargs):
        # Don't call parent init to avoid SDK dependency
        self._positions: Dict[str, Position] = {}
        self._mock_balance = 10000.0
        self._mock_prices = {'BTC': 95000.0, 'ETH': 3200.0, 'SOL': 180.0}
        self._order_counter = int(time.time())
        
        logger.info("=" * 50)
        logger.info("MOCK MODE - No real trades")
        logger.info(f"Balance: ${self._mock_balance:,.2f}")
        logger.info("=" * 50)
    
    async def close(self):
        pass
    
    async def get_balance(self) -> float:
        return self._mock_balance
    
    async def get_mark_price(self, symbol: str) -> float:
        base = self._mock_prices.get(symbol.upper(), 100.0)
        change = random.uniform(-0.005, 0.006)
        new_price = base * (1 + change)
        self._mock_prices[symbol.upper()] = new_price
        return new_price
    
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
        self._order_counter += 1
        
        pos = Position(
            symbol=symbol.upper(), side=side.lower(), size=size,
            entry_price=price, mark_price=price, leverage=leverage,
            margin=margin, unrealized_pnl=0, realized_pnl=0,
            liquidation_price=price * (0.5 if side == 'long' else 1.5),
            position_id=f"MOCK_{self._order_counter}"
        )
        self._positions[symbol.upper()] = pos
        self._mock_balance -= margin
        
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
        
        self._mock_balance += pos.margin + pnl
        del self._positions[symbol.upper()]
        
        logger.info(f"[MOCK] Closed {symbol} PnL: ${pnl:,.2f}")
        return {'success': True, 'pnl': pnl, 'mock': True}
    
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
        await self.get_positions()  # Update prices
        total = sum(p.unrealized_pnl for p in self._positions.values())
        margin = sum(p.margin for p in self._positions.values())
        return {
            'unrealized_pnl': total,
            'realized_pnl': 0,
            'total_pnl': total,
            'total_margin': margin,
            'pnl_percentage': (total / margin * 100) if margin > 0 else 0
        }
