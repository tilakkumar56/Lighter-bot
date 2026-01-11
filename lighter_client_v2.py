"""
Lighter.xyz API Client for Futures Trading
Using Official Lighter SDK
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
    
    # Market indices on Lighter
    MARKET_INDICES = {
        'BTC': 0,
        'ETH': 1,
        'SOL': 2,
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
        self._positions: Dict[str, Position] = {}
        self._order_counter = int(time.time())
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Lighter SDK clients"""
        if not LIGHTER_SDK_AVAILABLE:
            raise Exception("Lighter SDK not installed. Run: pip install lighter-sdk")
        
        try:
            # Clean up private key - remove 0x prefix if present
            pk = self.private_key.strip()
            if pk.startswith("0x"):
                pk = pk[2:]
            
            logger.info(f"Initializing Lighter client...")
            logger.info(f"  Base URL: {self.base_url}")
            logger.info(f"  Account Index: {self.account_index}")
            logger.info(f"  API Key Index: {self.api_key_index}")
            logger.info(f"  Private Key Length: {len(pk)} chars")
            
            # Initialize SignerClient for transactions
            # According to docs: api_private_keys={API_KEY_INDEX: PRIVATE_KEY}
            self._signer_client = lighter.SignerClient(
                url=self.base_url,
                api_private_keys={self.api_key_index: pk},
                account_index=self.account_index
            )
            
            # Initialize API clients
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
        """Get account information"""
        try:
            account = await self._account_api.account(index=self.account_index)
            return {
                'index': account.index,
                'collateral': float(account.collateral) if hasattr(account, 'collateral') else 0,
            }
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {}
    
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
            market_index = self.MARKET_INDICES.get(symbol.upper(), 0)
            orderbook = await self._order_api.order_book_details(market_index=market_index)
            
            if orderbook:
                best_ask = float(orderbook.best_ask) if hasattr(orderbook, 'best_ask') and orderbook.best_ask else 0
                best_bid = float(orderbook.best_bid) if hasattr(orderbook, 'best_bid') and orderbook.best_bid else 0
                if best_ask > 0 and best_bid > 0:
                    return (best_ask + best_bid) / 2
                return best_ask or best_bid
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get mark price: {e}")
            return 0.0
    
    async def get_positions(self) -> List[Position]:
        """Get all open positions"""
        # Update PnL for tracked positions
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
        """Open a position using market order"""
        try:
            market_index = self.MARKET_INDICES.get(symbol.upper(), 0)
            mark_price = await self.get_mark_price(symbol)
            
            if mark_price <= 0:
                raise Exception(f"Could not get valid price for {symbol}")
            
            # Calculate size
            notional = margin * leverage
            size = notional / mark_price
            
            # Convert to base amount (integer with precision)
            # Lighter uses specific decimal precision - check their docs
            base_amount = int(size * 1e8)
            
            is_buy = side.lower() == 'long'
            
            self._order_counter += 1
            client_order_index = self._order_counter
            
            logger.info(f"Opening {side} {symbol}: size={size:.6f}, price=${mark_price:,.2f}")
            
            # Use SignerClient to create market order
            result = await self._signer_client.create_market_order(
                market_index=market_index,
                base_amount=base_amount,
                is_buy=is_buy,
                client_order_index=client_order_index
            )
            
            # Track position
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
            
            logger.info(f"Position opened: {result}")
            return {'success': True, 'order_index': client_order_index}
            
        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            raise
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close a position"""
        pos = self._positions.get(symbol.upper())
        if not pos:
            raise Exception(f"No position for {symbol}")
        
        try:
            market_index = self.MARKET_INDICES.get(symbol.upper(), 0)
            mark_price = await self.get_mark_price(symbol)
            
            # Calculate PnL
            diff = mark_price - pos.entry_price
            if pos.side == 'short':
                diff = -diff
            pnl = (diff / pos.entry_price) * pos.margin * pos.leverage
            
            # Close by opposite order
            base_amount = int(pos.size * 1e8)
            is_buy = pos.side == 'short'  # Opposite
            
            self._order_counter += 1
            
            result = await self._signer_client.create_market_order(
                market_index=market_index,
                base_amount=base_amount,
                is_buy=is_buy,
                client_order_index=self._order_counter
            )
            
            del self._positions[symbol.upper()]
            
            logger.info(f"Position closed: PnL=${pnl:,.2f}")
            return {'success': True, 'pnl': pnl}
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            raise
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all positions"""
        results = []
        for symbol in list(self._positions.keys()):
            try:
                r = await self.close_position(symbol)
                results.append({'symbol': symbol, 'success': True, 'pnl': r.get('pnl', 0)})
            except Exception as e:
                results.append({'symbol': symbol, 'success': False, 'error': str(e)})
        return results
    
    async def get_total_pnl(self) -> Dict[str, float]:
        """Get total PnL"""
        positions = await self.get_positions()
        total_pnl = sum(p.unrealized_pnl for p in positions)
        total_margin = sum(p.margin for p in positions)
        return {
            'unrealized_pnl': total_pnl,
            'realized_pnl': 0,
            'total_pnl': total_pnl,
            'total_margin': total_margin,
            'pnl_percentage': (total_pnl / total_margin * 100) if total_margin > 0 else 0
        }


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
