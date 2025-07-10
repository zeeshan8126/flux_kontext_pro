#!/usr/bin/env python3
"""
ComfyUI NumPy Compatibility Fix

This script fixes the "RuntimeError: Numpy is not available" error
that occurs when PyTorch 2.1.0 is used with NumPy 2.x.

Usage: python fix_numpy_compatibility.py
"""

import subprocess
import sys
import importlib.util

def run_command(cmd):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def check_package_version(package_name):
    """Check if a package is installed and return its version."""
    try:
        spec = importlib.util.find_spec(package_name)
        if spec is None:
            return None
        
        module = importlib.import_module(package_name)
        return getattr(module, '__version__', 'unknown')
    except Exception:
        return None

def main():
    print("🔧 ComfyUI NumPy Compatibility Fix")
    print("=" * 50)
    
    # Check current versions
    numpy_version = check_package_version('numpy')
    torch_version = check_package_version('torch')
    
    print(f"Current NumPy version: {numpy_version}")
    print(f"Current PyTorch version: {torch_version}")
    
    if numpy_version is None:
        print("❌ NumPy is not installed!")
        return 1
    
    if torch_version is None:
        print("❌ PyTorch is not installed!")
        return 1
    
    # Check if we have the problematic combination
    if numpy_version.startswith('2.') and torch_version.startswith('2.1.'):
        print("\n🚨 ISSUE DETECTED: NumPy 2.x with PyTorch 2.1.x")
        print("This combination causes 'RuntimeError: Numpy is not available'")
        print("\n🔧 Fixing by downgrading NumPy to 1.x...")
        
        # Uninstall current NumPy
        print("Uninstalling current NumPy...")
        success, stdout, stderr = run_command("pip uninstall -y numpy")
        if not success:
            print(f"❌ Failed to uninstall NumPy: {stderr}")
            return 1
        
        # Install compatible NumPy version
        print("Installing NumPy < 2.0.0...")
        success, stdout, stderr = run_command("pip install 'numpy<2.0.0'")
        if not success:
            print(f"❌ Failed to install compatible NumPy: {stderr}")
            return 1
        
        # Verify the fix
        print("Verifying the fix...")
        try:
            import numpy as np
            import torch
            
            # Test compatibility
            test_array = np.array([1.0, 2.0, 3.0], dtype=np.float32)
            test_tensor = torch.from_numpy(test_array)
            
            print(f"✅ SUCCESS! NumPy {np.__version__} is now compatible with PyTorch {torch.__version__}")
            print("✅ torch.from_numpy() test passed")
            
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            return 1
    
    elif numpy_version.startswith('1.'):
        print("✅ NumPy version is already compatible (1.x)")
        
        # Still test compatibility
        try:
            import numpy as np
            import torch
            test_array = np.array([1.0, 2.0, 3.0], dtype=np.float32)
            test_tensor = torch.from_numpy(test_array)
            print("✅ NumPy-PyTorch compatibility test passed")
        except Exception as e:
            print(f"❌ Compatibility test failed: {e}")
            print("There may be another issue beyond NumPy version compatibility.")
            return 1
    
    else:
        print("ℹ️  Versions look compatible, but testing...")
        try:
            import numpy as np
            import torch
            test_array = np.array([1.0, 2.0, 3.0], dtype=np.float32)
            test_tensor = torch.from_numpy(test_array)
            print("✅ NumPy-PyTorch compatibility test passed")
        except Exception as e:
            print(f"❌ Compatibility test failed: {e}")
            print("You may need to check your specific PyTorch and NumPy versions.")
            return 1
    
    print("\n🎉 Fix completed! You can now run ComfyUI without the NumPy error.")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 