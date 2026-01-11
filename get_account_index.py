"""
Helper script to get your Lighter.xyz Account Index
"""
import asyncio

try:
    import lighter
except ImportError:
    print("=" * 50)
    print("ERROR: Lighter SDK not installed!")
    print("Run: pip install lighter-sdk")
    print("=" * 50)
    exit(1)


async def get_account_info(wallet_address: str):
    BASE_URL = "https://mainnet.zklighter.elliot.ai"
    
    print(f"\nQuerying Lighter.xyz for account: {wallet_address}")
    print("=" * 50)
    
    try:
        api = lighter.AccountApi(BASE_URL)
        account_data = await api.account(l1_address=wallet_address)
        
        print(f"\n✅ Account Found!")
        print(f"   Account Index: {account_data.index}")
        print(f"   L1 Address: {account_data.l1_address}")
        
        if hasattr(account_data, 'collateral'):
            print(f"   Collateral: {account_data.collateral}")
        
        print("\n" + "=" * 50)
        print("Add this to your .env file:")
        print(f"ACCOUNT_INDEX={account_data.index}")
        print("=" * 50)
        
        return account_data.index
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("1. Your wallet is connected to Lighter.xyz")
        print("2. You have made at least one transaction")
        print("3. The wallet address is correct")
        return None


def main():
    wallet = input("Enter your wallet address (0x...): ").strip()
    
    if not wallet.startswith("0x"):
        print("Invalid wallet address! Must start with 0x")
        return
    
    asyncio.run(get_account_info(wallet))


if __name__ == "__main__":
    main()
