#!/usr/bin/env python3
import sys
import os
from pathlib import Path

def validate_environment():
    """Validate required environment variables"""
    required = [
        "CACHE_DIR",
        "CACHE_SHARDS",
        "CACHE_LOCK_TIMEOUT",
    ]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        return False
    print("✅ Environment variables validated")
    return True

def validate_dependencies():
    """Validate Python dependencies"""
    try:
        import fastapi
        import crewai
        import filelock
        import structlog
        import msgpack
        print("✅ Core dependencies installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        return False

def validate_directory_structure():
    """Validate required directories"""
    required_dirs = [
        "backend",
        "backend/cache",
        "backend/orchestration",
        "backend/models",
        "backend/utils",
        "backend/cli",
        "backend/tests",
        "kubernetes",
    ]
    missing = [d for d in required_dirs if not Path(d).exists()]
    if missing:
        print(f"❌ Missing directories: {', '.join(missing)}")
        return False
    print("✅ Directory structure validated")
    return True

def validate_cache_directory():
    """Validate cache directory permissions"""
    cache_dir = os.getenv("CACHE_DIR", "/var/cache/network-ai")
    try:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        test_file = Path(cache_dir) / ".test_write"
        test_file.write_text("test")
        test_file.unlink()
        print(f"✅ Cache directory writable: {cache_dir}")
        return True
    except Exception as e:
        print(f"❌ Cache directory not writable: {e}")
        return False

if __name__ == "__main__":
    print("Running production validation...\n")
    
    checks = [
        validate_dependencies(),
        validate_directory_structure(),
        validate_environment(),
        validate_cache_directory(),
    ]
    
    if all(checks):
        print("\n✅ All validation checks passed")
        sys.exit(0)
    else:
        print("\n❌ Validation failed")
        sys.exit(1)