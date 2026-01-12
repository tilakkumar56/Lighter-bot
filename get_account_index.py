"""
Helper script to get your Lighter.xyz Account Index
"""
import asyncio

try:
    import lighter
    from lighter import ApiClient, Configuration, AccountApi
except ImportError:
    print("ERROR: Lighter SDK not installed!")
    print("Run: pip install lighter-sdk")
    exit(1)


async def get_account_info(wallet_address: str):
    BASE_URL = "https://mainnet.zklighter.elliot.ai"
    
    print(f"\nQuerying Lighter.xyz for account: {wallet_address}")
    print("=" * 50)
    
    try:
        # Create proper API client configuration
        config = Configuration(host=BASE_URL)
        api_client = ApiClient(config)
        api = AccountApi(api_client)
        
        # Try accounts_by_l1_address method
        accounts = await api.accounts_by_l1_address(wallet_address)
        
        print(f"\n✅ Account(s) Found!")
        print(f"   Response: {accounts}")
        
        if hasattr(accounts, 'accounts'):
            for acc in accounts.accounts:
                idx = acc.index if hasattr(acc, 'index') else acc.get('index', 'N/A')
                print(f"\n   Account Index: {idx}")
                print(f"   Add to .env: ACCOUNT_INDEX={idx}")
        elif isinstance(accounts, dict):
            print(f"   Account data: {accounts}")
        
    except AttributeError as e:
        print(f"SDK structure different, trying alternative...")
        try:
            # Maybe it's a simpler client
            print(f"\nLighter module contents: {[x for x in dir(lighter) if not x.startswith('_')]}")
        except Exception as e2:
            print(f"Error: {e2}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"Error type: {type(e)}")


def main():
    wallet = input("Enter your wallet address (0x...): ").strip()
    
    if not wallet.startswith("0x"):
        print("Invalid wallet address! Must start with 0x")
        return
    
    asyncio.run(get_account_info(wallet))


if __name__ == "__main__":
    main()
