"""
Lighter.xyz API Client for Futures Trading
"""
import os
import time
import hmac
import hashlib
import json
import logging
from typing import Optional, Dict, Any, List
from decimal import Decimal
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
    
    @property
    def pnl_percentage(self) -> float:
        if self.margin == 0:
            return 0.0
        return (self.unrealized_pnl / self.margin) * 100


@dataclass
class Order:
    """Represents a trading order"""
    order_id: str
    symbol: str
    side: str
    order_type: str
    size: float
    price: Optional[float]
    status: str
    filled_size: float = 0.0
    avg_fill_price: float = 0.0


class LighterClient:
    """
    Client for interacting with Lighter.xyz futures trading API
    """
    
    # Supported trading pairs
    SUPPORTED_ASSETS = ['BTC', 'ETH', 'SOL']
    TRADING_PAIRS = {
        'BTC': 'BTC-USD',
        'ETH': 'ETH-USD', 
        'SOL': 'SOL-USD'
    }
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        wallet_address: str,
        base_url: str = "https://api.lighter.xyz"
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.wallet_address = wallet_address
        self.base_url = base_url.rstrip('/')
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the client session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate HMAC signature for API authentication"""
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _get_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """Generate authenticated headers"""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, path, body)
        
        return {
            "Content-Type": "application/json",
            "X-API-KEY": self.api_key,
            "X-TIMESTAMP": timestamp,
            "X-SIGNATURE": signature,
            "X-WALLET-ADDRESS": self.wallet_address
        }
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make authenticated API request"""
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
                    logger.error(f"API Error: {response.status} - {error_msg}")
                    raise Exception(f"API Error: {error_msg}")
                
                return result
                
        except aiohttp.ClientError as e:
            logger.error(f"Request failed: {e}")
            raise Exception(f"Request failed: {e}")
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information including balance"""
        return await self._request("GET", "/account")
    
    async def get_balance(self) -> float:
        """Get available balance in USD"""
        try:
            account = await self.get_account_info()
            return float(account.get('availableBalance', 0))
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker/price for a symbol"""
        pair = self.TRADING_PAIRS.get(symbol.upper(), f"{symbol.upper()}-USD")
        return await self._request("GET", f"/ticker/{pair}")
    
    async def get_mark_price(self, symbol: str) -> float:
        """Get current mark price for a symbol"""
        try:
            ticker = await self.get_ticker(symbol)
            return float(ticker.get('markPrice', ticker.get('lastPrice', 0)))
        except Exception as e:
            logger.error(f"Failed to get mark price for {symbol}: {e}")
            return 0.0
    
    async def get_positions(self) -> List[Position]:
        """Get all open positions"""
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
            
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol"""
        positions = await self.get_positions()
        symbol_upper = symbol.upper()
        
        for pos in positions:
            if pos.symbol.upper() == symbol_upper:
                return pos
        
        return None
    
    async def open_position(
        self,
        symbol: str,
        side: str,  # 'long' or 'short'
        margin: float,
        leverage: int
    ) -> Dict[str, Any]:
        """
        Open a new futures position
        
        Args:
            symbol: Asset symbol (BTC, ETH, SOL)
            side: 'long' or 'short'
            margin: Margin amount in USD
            leverage: Leverage multiplier (1-100)
        
        Returns:
            Order result dictionary
        """
        pair = self.TRADING_PAIRS.get(symbol.upper(), f"{symbol.upper()}-USD")
        
        # Calculate position size based on mark price
        mark_price = await self.get_mark_price(symbol)
        if mark_price <= 0:
            raise Exception(f"Could not get valid price for {symbol}")
        
        # Position size = (margin * leverage) / mark_price
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
        
        logger.info(f"Opening {side} position: {symbol} | Margin: ${margin} | Leverage: {leverage}x | Size: {size}")
        
        return await self._request("POST", "/orders", order_data)
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """
        Close an existing position (market order)
        
        Args:
            symbol: Asset symbol (BTC, ETH, SOL)
        
        Returns:
            Order result dictionary
        """
        position = await self.get_position(symbol)
        if not position:
            raise Exception(f"No open position found for {symbol}")
        
        pair = self.TRADING_PAIRS.get(symbol.upper(), f"{symbol.upper()}-USD")
        
        # Close by opening opposite position
        close_side = "sell" if position.side == "long" else "buy"
        
        order_data = {
            "symbol": pair,
            "side": close_side,
            "type": "market",
            "size": str(position.size),
            "reduceOnly": True
        }
        
        logger.info(f"Closing position: {symbol} | Side: {position.side} | Size: {position.size}")
        
        return await self._request("POST", "/orders", order_data)
    
    async def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all open positions"""
        positions = await self.get_positions()
        results = []
        
        for pos in positions:
            try:
                result = await self.close_position(pos.symbol)
                results.append({
                    'symbol': pos.symbol,
                    'success': True,
                    'pnl': pos.unrealized_pnl,
                    'result': result
                })
            except Exception as e:
                results.append({
                    'symbol': pos.symbol,
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    async def get_total_pnl(self) -> Dict[str, float]:
        """Get total PnL across all positions"""
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
    
    async def check_profit_target(self, target_usd: float) -> bool:
        """Check if profit target has been reached"""
        pnl = await self.get_total_pnl()
        return pnl['unrealized_pnl'] >= target_usd


class MockLighterClient(LighterClient):
    """
    Mock client for testing without real API connection
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_positions: List[Position] = []
        self._mock_balance = 10000.0
        self._mock_prices = {
            'BTC': 45000.0,
            'ETH': 2500.0,
            'SOL': 100.0
        }
    
    async def get_balance(self) -> float:
        return self._mock_balance
    
    async def get_mark_price(self, symbol: str) -> float:
        # Simulate small price movement
        import random
        base_price = self._mock_prices.get(symbol.upper(), 100.0)
        variation = base_price * random.uniform(-0.001, 0.001)
        return base_price + variation
    
    async def get_positions(self) -> List[Position]:
        # Update unrealized PnL based on price changes
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
