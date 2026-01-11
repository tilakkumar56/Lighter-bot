"""
Helper script to get your Lighter.xyz Account Index
"""
import asyncio

try:
    import lighter
except ImportError:
    print("ERROR: Lighter SDK not installed!")
    print("Run: pip install lighter-sdk")
    exit(1)


async def get_account_info(wallet_address: str):
    BASE_URL = "https://mainnet.zklighter.elliot.ai"
    
    print(f"\nQuerying Lighter.xyz for account: {wallet_address}")
    print("=" * 50)
    
    try:
        api = lighter.AccountApi(BASE_URL)
        
        # Try accounts_by_l1_address method
        accounts = await api.accounts_by_l1_address(wallet_address)
        
        if accounts:
            print(f"\n✅ Account(s) Found!")
            
            # Handle if it's a list or single object
            if isinstance(accounts, list):
                for acc in accounts:
                    print(f"   Account Index: {acc.index if hasattr(acc, 'index') else acc}")
            else:
                print(f"   Account Data: {accounts}")
                if hasattr(accounts, 'index'):
                    print(f"   Account Index: {accounts.index}")
                elif hasattr(accounts, 'accounts'):
                    for acc in accounts.accounts:
                        print(f"   Account Index: {acc.index}")
            
            print("\n" + "=" * 50)
        else:
            print("No accounts found")
        
    except Exception as e:
        print(f"\n❌ Error with accounts_by_l1_address: {e}")
        
        # Try alternative approach
        print("\nTrying alternative method...")
        try:
            # Check available methods
            print(f"Available AccountApi methods: {[m for m in dir(api) if not m.startswith('_')]}")
        except:
            pass


def main():
    wallet = input("Enter your wallet address (0x...): ").strip()
    
    if not wallet.startswith("0x"):
        print("Invalid wallet address! Must start with 0x")
        return
    
    asyncio.run(get_account_info(wallet))


if __name__ == "__main__":
    main()
