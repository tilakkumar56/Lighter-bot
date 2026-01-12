"""
Test SignerClient.create_market_order signature
"""
import inspect
import lighter

print("=" * 60)
print("SignerClient.create_market_order signature:")
print("=" * 60)

try:
    sig = inspect.signature(lighter.SignerClient.create_market_order)
    print(f"\n{sig}\n")
    
    for name, param in sig.parameters.items():
        if name != 'self':
            default = param.default if param.default != inspect.Parameter.empty else 'required'
            print(f"  - {name}: {default}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("All SignerClient methods with 'order':")
print("=" * 60)

for method in dir(lighter.SignerClient):
    if 'order' in method.lower() and not method.startswith('_'):
        print(f"  - {method}")
        try:
            sig = inspect.signature(getattr(lighter.SignerClient, method))
            print(f"    {sig}")
        except:
            pass
