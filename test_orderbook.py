"""
Test OrderApi to get correct method signature
"""
import asyncio
import inspect

import lighter
from lighter import ApiClient, Configuration, OrderApi

BASE_URL = "https://mainnet.zklighter.elliot.ai"


async def main():
    print("=" * 60)
    print("TESTING ORDER API")
    print("=" * 60)
    
    config = Configuration(host=BASE_URL)
    api_client = ApiClient(config)
    order_api = OrderApi(api_client)
    
    # Check order_book_details signature
    print("\n📖 order_book_details signature:")
    try:
        sig = inspect.signature(order_api.order_book_details)
        print(f"   {sig}")
        for name, param in sig.parameters.items():
            print(f"   - {name}: {param.default if param.default != inspect.Parameter.empty else 'required'}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Check order_books signature
    print("\n📖 order_books signature:")
    try:
        sig = inspect.signature(order_api.order_books)
        print(f"   {sig}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Try to get orderbooks
    print("\n🔍 Fetching orderbooks...")
    try:
        result = await order_api.order_books()
        print(f"   Result type: {type(result)}")
        print(f"   Result: {result}")
        
        if hasattr(result, 'order_books'):
            print(f"\n   Found {len(result.order_books)} markets:")
            for i, ob in enumerate(result.order_books[:5]):  # First 5
                print(f"   [{i}] {ob}")
    except Exception as e:
        print(f"   Error: {e}")
    
    await api_client.close()


if __name__ == "__main__":
    asyncio.run(main())
