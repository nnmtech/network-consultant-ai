#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path

def check_requirements():
    """Validate all required files exist"""
    required_files = [
        "requirements.txt",
        "backend/main.py",
        "backend/cache/robust_cache.py",
        "backend/orchestration/enhanced_orchestrator.py",
        "kubernetes/network-consultant-enterprise.yaml",
    ]
    
    missing = [f for f in required_files if not Path(f).exists()]
    if missing:
        print(f"❌ Missing required files: {missing}")
        return False
    print("✅ All required files present")
    return True

def check_dependencies():
    """Verify Python dependencies are installable"""
    try:
        result = subprocess.run(
            ["pip", "check"],
            capture_output=True,
            text=True,
            check=True
        )
        print("✅ Dependencies validated")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Dependency check failed: {e.stderr}")
        return False

def check_syntax():
    """Run Python syntax validation"""
    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", "backend/main.py"],
            capture_output=True,
            text=True,
            check=True
        )
        print("✅ Python syntax valid")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Syntax error: {e.stderr}")
        return False

def main():
    print("🔍 Network Consultant AI - Production Validation\n")
    
    checks = [
        ("Requirements", check_requirements),
        ("Dependencies", check_dependencies),
        ("Syntax", check_syntax),
    ]
    
    results = []
    for name, check in checks:
        print(f"\n{'='*50}")
        print(f"Checking: {name}")
        print('='*50)
        results.append(check())
    
    print("\n" + "="*50)
    if all(results):
        print("✅ ALL VALIDATION CHECKS PASSED")
        print("🚀 System ready for production deployment")
        return 0
    else:
        print("❌ VALIDATION FAILED")
        print("🛑 Fix issues before deploying to production")
        return 1

if __name__ == "__main__":
    sys.exit(main())