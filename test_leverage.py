"""
Test update_leverage signature
"""
import inspect
import lighter

print("=" * 60)
print("update_leverage signature:")
print("=" * 60)

try:
    sig = inspect.signature(lighter.SignerClient.update_leverage)
    print(f"\n{sig}\n")
    
    for name, param in sig.parameters.items():
        if name != 'self':
            default = param.default if param.default != inspect.Parameter.empty else 'required'
            print(f"  - {name}: {default}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("update_margin signature:")
print("=" * 60)

try:
    sig = inspect.signature(lighter.SignerClient.update_margin)
    print(f"\n{sig}\n")
    
    for name, param in sig.parameters.items():
        if name != 'self':
            default = param.default if param.default != inspect.Parameter.empty else 'required'
            print(f"  - {name}: {default}")
except Exception as e:
    print(f"Error: {e}")
