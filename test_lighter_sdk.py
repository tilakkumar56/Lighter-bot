"""
Test Lighter SDK to understand key format
"""
import asyncio
import inspect

try:
    import lighter
    print("✅ Lighter SDK imported successfully")
    print(f"   Version: {lighter.__version__ if hasattr(lighter, '__version__') else 'unknown'}")
except ImportError:
    print("❌ Lighter SDK not installed")
    print("Run: pip install lighter-sdk")
    exit(1)

print("\n" + "=" * 60)
print("LIGHTER SDK INSPECTION")
print("=" * 60)

# List all main classes
print("\n📦 Main Classes in lighter module:")
for name in dir(lighter):
    if not name.startswith('_'):
        obj = getattr(lighter, name)
        if isinstance(obj, type):
            print(f"   - {name}")

# Check SignerClient
print("\n" + "=" * 60)
print("🔐 SignerClient Details:")
print("=" * 60)

if hasattr(lighter, 'SignerClient'):
    SignerClient = lighter.SignerClient
    
    # Get __init__ signature
    try:
        sig = inspect.signature(SignerClient.__init__)
        print(f"\n__init__ parameters:")
        for param_name, param in sig.parameters.items():
            if param_name != 'self':
                default = param.default if param.default != inspect.Parameter.empty else 'required'
                print(f"   - {param_name}: {default}")
    except Exception as e:
        print(f"   Could not get signature: {e}")
    
    # List methods
    print(f"\nMethods:")
    for method in dir(SignerClient):
        if not method.startswith('_') and callable(getattr(SignerClient, method, None)):
            print(f"   - {method}")
else:
    print("   SignerClient not found")

# Try to find examples or documentation
print("\n" + "=" * 60)
print("📖 Looking for documentation...")
print("=" * 60)

if hasattr(lighter, '__doc__') and lighter.__doc__:
    print(lighter.__doc__[:500])
else:
    print("No module documentation found")

# Check for any example files or constants
print("\n" + "=" * 60)
print("🔧 Constants and Examples:")
print("=" * 60)

for name in dir(lighter):
    obj = getattr(lighter, name)
    if isinstance(obj, str) and not name.startswith('_'):
        print(f"   {name} = '{obj}'")
    elif isinstance(obj, int) and not name.startswith('_'):
        print(f"   {name} = {obj}")

print("\n" + "=" * 60)
print("🧪 Testing SignerClient Initialization:")
print("=" * 60)

# Test with a dummy key to see exact error
BASE_URL = "https://mainnet.zklighter.elliot.ai"
DUMMY_64_CHAR_KEY = "a" * 64  # 64 hex chars = 32 bytes
DUMMY_40_CHAR_KEY = "a" * 40  # 40 hex chars = 20 bytes

print(f"\nTrying with 64-character key...")
try:
    client = lighter.SignerClient(
        url=BASE_URL,
        api_private_keys={10: DUMMY_64_CHAR_KEY},
        account_index=703156
    )
    print("   ✅ 64-char key accepted!")
except Exception as e:
    print(f"   ❌ Error: {e}")

print(f"\nTrying with 40-character key...")
try:
    client = lighter.SignerClient(
        url=BASE_URL,
        api_private_keys={10: DUMMY_40_CHAR_KEY},
        account_index=703156
    )
    print("   ✅ 40-char key accepted!")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
