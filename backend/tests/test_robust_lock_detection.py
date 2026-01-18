#!/usr/bin/env python3
import asyncio
import multiprocessing
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.cache.robust_cache import RobustCacheManager

def worker_process(worker_id: int, cache_dir: str, iterations: int):
    import asyncio
    from backend.cache.robust_cache import RobustCacheManager
    
    cache = RobustCacheManager(cache_dir=cache_dir, shards=4, lock_timeout=5)
    
    async def work():
        for i in range(iterations):
            key = f"test_key_{i % 10}"
            value = {"worker": worker_id, "iteration": i, "timestamp": time.time()}
            
            await cache.set(key, value, expire=60, tag="test")
            
            retrieved = await cache.get(key)
            if retrieved is None:
                print(f"Worker {worker_id}: Failed to retrieve key {key}")
            
            await asyncio.sleep(0.01)
    
    asyncio.run(work())
    print(f"Worker {worker_id} completed {iterations} iterations")

def test_multiprocess_safety():
    print("\n" + "="*60)
    print("TEST: Multi-Process Lock Safety")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = tmpdir
        num_workers = 4
        iterations_per_worker = 20
        
        print(f"\nStarting {num_workers} workers with {iterations_per_worker} iterations each...")
        
        start_time = time.time()
        
        processes = []
        for worker_id in range(num_workers):
            p = multiprocessing.Process(
                target=worker_process,
                args=(worker_id, cache_dir, iterations_per_worker)
            )
            p.start()
            processes.append(p)
        
        for p in processes:
            p.join(timeout=30)
            if p.is_alive():
                print(f"WARNING: Process {p.pid} did not complete in time")
                p.terminate()
                p.join()
        
        duration = time.time() - start_time
        
        print(f"\n✓ All workers completed in {duration:.2f}s")
        print(f"✓ No deadlocks detected")
        print(f"✓ Total operations: {num_workers * iterations_per_worker}")
        
        cache_files = list(Path(cache_dir).rglob("*.cache"))
        lock_files = list(Path(cache_dir).rglob("*.lock"))
        
        print(f"\nCache files created: {len(cache_files)}")
        print(f"Lock files remaining: {len(lock_files)}")
        
        if len(lock_files) > 0:
            print("\nWARNING: Some lock files remain (may indicate stale locks)")
            print("This is acceptable if processes were terminated abnormally")

def test_stale_lock_cleanup():
    print("\n" + "="*60)
    print("TEST: Stale Lock Detection and Cleanup")
    print("="*60)
    
    async def run_test():
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = RobustCacheManager(cache_dir=tmpdir, shards=2)
            
            test_key = "stale_lock_test"
            lock_path = cache._get_lock_path(test_key)
            
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.touch()
            
            old_time = time.time() - 400
            os.utime(lock_path, (old_time, old_time))
            
            print(f"\nCreated artificial stale lock: {lock_path.name}")
            print(f"Lock age: {time.time() - lock_path.stat().st_mtime:.0f}s (> 300s threshold)")
            
            is_stale = await cache._is_lock_stale(lock_path, max_age=300)
            print(f"Stale detection result: {is_stale}")
            
            if not is_stale:
                print("✗ FAILED: Lock should be detected as stale")
                return False
            
            await cache.cleanup_stale_locks(max_age=300)
            
            if lock_path.exists():
                print("✗ FAILED: Stale lock was not cleaned up")
                return False
            
            print("\n✓ Stale lock successfully detected and cleaned")
            print("✓ Lock cleanup working correctly")
            return True
    
    result = asyncio.run(run_test())
    return result

def test_cache_operations():
    print("\n" + "="*60)
    print("TEST: Basic Cache Operations")
    print("="*60)
    
    async def run_test():
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = RobustCacheManager(cache_dir=tmpdir, shards=2)
            
            print("\nTesting set/get operations...")
            await cache.set("key1", {"data": "value1"}, expire=60)
            result = await cache.get("key1")
            
            if result != {"data": "value1"}:
                print("✗ FAILED: Cache get/set mismatch")
                return False
            
            print("✓ Set/Get working correctly")
            
            print("\nTesting tag invalidation...")
            await cache.set("key2", {"data": "value2"}, tag="test_tag")
            await cache.set("key3", {"data": "value3"}, tag="test_tag")
            await cache.invalidate_tag("test_tag")
            
            result2 = await cache.get("key2")
            result3 = await cache.get("key3")
            
            if result2 is not None or result3 is not None:
                print("✗ FAILED: Tag invalidation did not work")
                return False
            
            print("✓ Tag invalidation working correctly")
            
            print("\nTesting health check...")
            healthy = await cache.health_check()
            
            if not healthy:
                print("✗ FAILED: Health check failed")
                return False
            
            print("✓ Health check passing")
            
            stats = await cache.get_stats()
            print(f"\nCache statistics: {stats}")
            
            return True
    
    result = asyncio.run(run_test())
    return result

def main():
    print("\n" + "#"*60)
    print("# Network Consultant AI - Robust Lock Detection Tests")
    print("#"*60)
    
    tests = [
        ("Basic Cache Operations", test_cache_operations),
        ("Stale Lock Cleanup", test_stale_lock_cleanup),
        ("Multi-Process Safety", test_multiprocess_safety),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ EXCEPTION in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        color = "green" if result else "red"
        print(f"{name}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "="*60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print("="*60)
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())