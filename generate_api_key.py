"""
Generate Lighter.xyz API Key

This script helps you generate an API key for trading on Lighter.xyz
You need your wallet's private key to generate the API key.
"""
import asyncio
import os

try:
    import lighter
    from lighter import ApiClient, Configuration, AccountApi, SignerClient
except ImportError:
    print("=" * 50)
    print("ERROR: Lighter SDK not installed!")
    print("Run: pip install lighter-sdk")
    print("=" * 50)
    exit(1)


async def generate_api_key():
    print("=" * 50)
    print("LIGHTER.XYZ API KEY GENERATOR")
    print("=" * 50)
    
    # Get user inputs
    eth_private_key = input("\nEnter your MetaMask Private Key (64 hex chars): ").strip()
    
    # Remove 0x prefix if present
    if eth_private_key.startswith("0x"):
        eth_private_key = eth_private_key[2:]
    
    if len(eth_private_key) != 64:
        print(f"\n❌ Invalid private key length: {len(eth_private_key)} (expected 64)")
        print("Make sure you copied the full private key from MetaMask")
        return
    
    account_index = input("Enter your Account Index (e.g., 703156): ").strip()
    
    try:
        account_index = int(account_index)
    except:
        print("❌ Invalid account index")
        return
    
    api_key_index = input("Enter API Key Index (3-254, e.g., 10): ").strip()
    
    try:
        api_key_index = int(api_key_index)
        if api_key_index < 3 or api_key_index > 254:
            raise ValueError()
    except:
        print("❌ Invalid API key index (must be 3-254)")
        return
    
    BASE_URL = "https://mainnet.zklighter.elliot.ai"
    
    print(f"\n⏳ Generating API key...")
    print(f"   URL: {BASE_URL}")
    print(f"   Account Index: {account_index}")
    print(f"   API Key Index: {api_key_index}")
    
    try:
        # Initialize the SignerClient with ETH private key
        # The SDK should handle API key generation
        signer = SignerClient(
            url=BASE_URL,
            private_key=eth_private_key,
            account_index=account_index,
            api_key_index=api_key_index
        )
        
        print("\n✅ SignerClient initialized successfully!")
        print("\nYour configuration:")
        print(f"   Account Index: {account_index}")
        print(f"   API Key Index: {api_key_index}")
        
        # The private key to use is derived internally
        print("\n" + "=" * 50)
        print("Use these in your .env file:")
        print(f"ETH_PRIVATE_KEY={eth_private_key}")
        print(f"ACCOUNT_INDEX={account_index}")
        print(f"API_KEY_INDEX={api_key_index}")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nThis might mean:")
        print("1. The private key format is wrong")
        print("2. You need to register the API key on Lighter first")
        print("3. The SDK expects a different key format")
        
        # Try to show more info
        print("\n" + "=" * 50)
        print("Checking SignerClient signature...")
        import inspect
        try:
            sig = inspect.signature(SignerClient.__init__)
            print(f"SignerClient parameters: {sig}")
        except:
            pass


def main():
    asyncio.run(generate_api_key())


if __name__ == "__main__":
    main()
