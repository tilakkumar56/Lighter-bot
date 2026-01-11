"""
Helper script to get your Lighter.xyz Account Index
Run this first before using the trading bot!
"""

# First, install the SDK:
# pip install lighter-sdk

try:
    import lighter
except ImportError:
    print("=" * 50)
    print("ERROR: Lighter SDK not installed!")
    print("Run: pip install lighter-sdk")
    print("=" * 50)
    exit(1)

# Replace with your wallet address
WALLET_ADDRESS = input("Enter your wallet address (0x...): ").strip()

if not WALLET_ADDRESS.startswith("0x"):
    print("Invalid wallet address!")
    exit(1)

BASE_URL = "https://mainnet.zklighter.elliot.ai"

print(f"\nQuerying Lighter.xyz for account: {WALLET_ADDRESS}")
print("=" * 50)

try:
    api = lighter.AccountApi(BASE_URL)
    account_data = api.account(l1_address=WALLET_ADDRESS)
    
    print(f"\n✅ Account Found!")
    print(f"   Account Index: {account_data.index}")
    print(f"   L1 Address: {account_data.l1_address}")
    
    if hasattr(account_data, 'collateral'):
        print(f"   Collateral: {account_data.collateral}")
    
    print("\n" + "=" * 50)
    print("Add this to your .env file:")
    print(f"ACCOUNT_INDEX={account_data.index}")
    print("=" * 50)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nMake sure:")
    print("1. Your wallet is connected to Lighter.xyz")
    print("2. You have made at least one transaction")
    print("3. The wallet address is correct")
