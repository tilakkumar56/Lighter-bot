"""
Test getting price from Lighter
"""
import asyncio
import lighter
from lighter import ApiClient, Configuration, OrderApi

BASE_URL = "https://mainnet.zklighter.elliot.ai"

async def main():
    config = Configuration(host=BASE_URL)
    api_client = ApiClient(config)
    order_api = OrderApi(api_client)
    
    # BTC market_id = 1
    print("=" * 60)
    print("Getting BTC orderbook (market_id=1)")
    print("=" * 60)
    
    try:
        result = await order_api.order_book_details(market_id=1)
        print(f"\nResult type: {type(result)}")
        print(f"\nFull result:\n{result}")
        
        # List all attributes
        print(f"\nAttributes:")
        for attr in dir(result):
            if not attr.startswith('_'):
                try:
                    val = getattr(result, attr)
                    if not callable(val):
                        print(f"  {attr} = {val}")
                except:
                    pass
                    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    await api_client.close()

if __name__ == "__main__":
    asyncio.run(main())
