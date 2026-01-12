"""
Test Lighter SDK with async
"""
import asyncio

try:
    import lighter
except ImportError:
    print("❌ Run: pip install lighter-sdk")
    exit(1)

BASE_URL = "https://mainnet.zklighter.elliot.ai"


async def test_with_key(key: str, key_index: int, account_index: int):
    """Test SignerClient initialization"""
    print(f"\nTrying key ({len(key)} chars)...")
    
    try:
        client = lighter.SignerClient(
            url=BASE_URL,
            api_private_keys={key_index: key},
            account_index=account_index
        )
        print("   ✅ SignerClient created successfully!")
        
        # Try to get nonce to verify it works
        try:
            nonce = await client.get_api_key_nonce(key_index)
            print(f"   ✅ Nonce retrieved: {nonce}")
        except Exception as e:
            print(f"   ⚠️ Could not get nonce: {e}")
        
        await client.close()
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


async def main():
    print("=" * 60)
    print("LIGHTER SDK KEY FORMAT TEST")
    print("=" * 60)
    
    # Get user input
    private_key = input("\nEnter your ETH Private Key (from MetaMask): ").strip()
    
    # Remove 0x if present
    if private_key.startswith("0x"):
        private_key = private_key[2:]
    
    print(f"\nKey length: {len(private_key)} characters")
    
    account_index = int(input("Enter Account Index (703156): ").strip() or "703156")
    api_key_index = int(input("Enter API Key Index (3-254, default 10): ").strip() or "10")
    
    print("\n" + "=" * 60)
    print("Testing different key formats...")
    print("=" * 60)
    
    # Test 1: Full key as-is
    print("\n[Test 1] Using key as-is:")
    success = await test_with_key(private_key, api_key_index, account_index)
    
    if not success and len(private_key) == 64:
        # Test 2: Maybe they want first 40 chars?
        print("\n[Test 2] Using first 40 characters:")
        await test_with_key(private_key[:40], api_key_index, account_index)
        
        # Test 3: Last 40 chars?
        print("\n[Test 3] Using last 40 characters:")
        await test_with_key(private_key[-40:], api_key_index, account_index)
    
    print("\n" + "=" * 60)
    print("If all tests failed, you may need to register the API key first")
    print("on Lighter.xyz or use a different method.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
