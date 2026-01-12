"""
Test script to see what account data Lighter.xyz returns
Run this on your server after opening positions to debug PnL tracking
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    try:
        import lighter
        from lighter import ApiClient, Configuration, AccountApi, OrderApi
    except ImportError:
        print("ERROR: lighter-sdk not installed")
        return
    
    account_index = int(os.getenv('ACCOUNT_INDEX', '0'))
    base_url = os.getenv('LIGHTER_BASE_URL', 'https://mainnet.zklighter.elliot.ai')
    
    print(f"\n{'='*60}")
    print(f"Testing Lighter.xyz Account Data")
    print(f"{'='*60}")
    print(f"Account Index: {account_index}")
    print(f"Base URL: {base_url}")
    print()
    
    config = Configuration(host=base_url)
    api_client = ApiClient(config)
    account_api = AccountApi(api_client)
    order_api = OrderApi(api_client)
    
    try:
        # Get account data
        print("Fetching account data...")
        account = await account_api.account(account_index)
        
        print(f"\n{'='*60}")
        print("RAW ACCOUNT DATA:")
        print(f"{'='*60}")
        
        # Print all attributes
        for attr in dir(account):
            if not attr.startswith('_'):
                try:
                    value = getattr(account, attr)
                    if not callable(value):
                        print(f"  {attr}: {value}")
                except:
                    pass
        
        # Specifically look for position-related fields
        print(f"\n{'='*60}")
        print("POSITION FIELDS:")
        print(f"{'='*60}")
        
        position_attrs = ['positions', 'open_positions', 'position', 'unrealized_pnl', 
                         'pnl', 'total_pnl', 'margin', 'collateral', 'equity',
                         'account_value', 'free_collateral', 'initial_margin']
        
        for attr in position_attrs:
            if hasattr(account, attr):
                value = getattr(account, attr)
                print(f"  {attr}: {value}")
                
                # If it's a list, print each item
                if isinstance(value, list) and len(value) > 0:
                    print(f"    Found {len(value)} items:")
                    for i, item in enumerate(value):
                        print(f"    [{i}]: {item}")
                        # Print item attributes
                        for item_attr in dir(item):
                            if not item_attr.startswith('_'):
                                try:
                                    item_value = getattr(item, item_attr)
                                    if not callable(item_value):
                                        print(f"        {item_attr}: {item_value}")
                                except:
                                    pass
        
        # Get current prices
        print(f"\n{'='*60}")
        print("CURRENT PRICES:")
        print(f"{'='*60}")
        
        for symbol, market_id in [('ETH', 0), ('BTC', 1), ('SOL', 2)]:
            try:
                result = await order_api.order_book_details(market_id=market_id)
                if result and hasattr(result, 'order_book_details') and result.order_book_details:
                    ob = result.order_book_details[0]
                    price = getattr(ob, 'last_trade_price', 'N/A')
                    print(f"  {symbol} (market_id={market_id}): ${price}")
            except Exception as e:
                print(f"  {symbol}: Error - {e}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await api_client.close()
    
    print(f"\n{'='*60}")
    print("DONE")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    asyncio.run(main())
