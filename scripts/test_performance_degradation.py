#!/usr/bin/env python3
"""Performance degradation test for LawnBerry Pi v2 telemetry endpoints.

Tests telemetry latency against platform-specific guardrails:
- Raspberry Pi 5: ≤250ms target
- Raspberry Pi 4B: ≤350ms target (graceful degradation)

Usage:
    python scripts/test_performance_degradation.py [--target TARGET_MS] [--device DEVICE]
    
Examples:
    # Test with Pi 5 target (250ms)
    python scripts/test_performance_degradation.py --target 0.25
    
    # Test with Pi 4B target (350ms)
    python scripts/test_performance_degradation.py --target 0.35 --device pi4
"""
import time
import statistics
import httpx
import argparse
import sys

BASE = "http://127.0.0.1:8001"

def detect_platform():
    """Detect Raspberry Pi platform (simplified detection)"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            if 'BCM2712' in cpuinfo:  # Pi 5
                return 'pi5'
            elif 'BCM2711' in cpuinfo:  # Pi 4B
                return 'pi4'
    except:
        pass
    return 'unknown'

def run_latency_test(base_url: str, num_samples: int = 20):
    """Run latency test against dashboard telemetry endpoint"""
    latencies = []
    
    print(f"Running {num_samples} latency samples...")
    
    with httpx.Client(timeout=5.0) as client:
        for i in range(num_samples):
            t0 = time.perf_counter()
            try:
                r = client.get(f"{base_url}/api/v2/dashboard/telemetry")
                r.raise_for_status()
                dt_ms = (time.perf_counter() - t0) * 1000
                latencies.append(dt_ms)
                
                # Check if response includes latency from server
                data = r.json()
                server_latency = data.get('latency_ms')
                if server_latency:
                    print(f"  Sample {i+1}: {dt_ms:.2f}ms (server: {server_latency:.2f}ms)")
                else:
                    print(f"  Sample {i+1}: {dt_ms:.2f}ms")
                    
            except Exception as e:
                print(f"  Sample {i+1}: FAILED - {e}")
                
            time.sleep(0.05)
    
    return latencies

def analyze_results(latencies: list, target_ms: float, device: str):
    """Analyze latency results against target"""
    if not latencies:
        print("ERROR: No successful latency measurements")
        return False
    
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(0.95 * len(latencies)) - 1] if len(latencies) > 1 else latencies[0]
    p99 = sorted(latencies)[int(0.99 * len(latencies)) - 1] if len(latencies) > 1 else latencies[0]
    avg = statistics.mean(latencies)
    max_latency = max(latencies)
    min_latency = min(latencies)
    
    print("\n=== Latency Results ===")
    print(f"Device: {device}")
    print(f"Target: {target_ms:.2f}ms")
    print(f"Samples: {len(latencies)}")
    print(f"\nStatistics:")
    print(f"  Min:    {min_latency:.2f}ms")
    print(f"  P50:    {p50:.2f}ms")
    print(f"  Avg:    {avg:.2f}ms")
    print(f"  P95:    {p95:.2f}ms")
    print(f"  P99:    {p99:.2f}ms")
    print(f"  Max:    {max_latency:.2f}ms")
    
    # Check against target
    meets_target = p95 <= target_ms
    
    print(f"\nTarget Check: {'PASS' if meets_target else 'FAIL'}")
    if not meets_target:
        print(f"  P95 latency ({p95:.2f}ms) exceeds target ({target_ms:.2f}ms)")
        print(f"  See docs/OPERATIONS.md#telemetry-latency-troubleshooting for remediation")
    
    return meets_target

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test telemetry latency performance')
    parser.add_argument('--target', type=float, default=None,
                       help='Target latency in seconds (e.g., 0.25 for 250ms)')
    parser.add_argument('--device', type=str, default=None,
                       choices=['pi5', 'pi4', 'auto'],
                       help='Device type (auto-detects if not specified)')
    parser.add_argument('--samples', type=int, default=20,
                       help='Number of latency samples to collect')
    parser.add_argument('--base-url', type=str, default=BASE,
                       help='Base URL for API server')
    
    args = parser.parse_args()
    
    # Detect or use specified device
    if args.device == 'auto' or args.device is None:
        device = detect_platform()
        print(f"Detected platform: {device}")
    else:
        device = args.device
    
    # Set target based on device if not specified
    if args.target is None:
        if device == 'pi5':
            target_seconds = 0.25  # 250ms
        elif device == 'pi4':
            target_seconds = 0.35  # 350ms
        else:
            target_seconds = 0.25  # Default to Pi 5 target
            print(f"WARNING: Unknown device, using default target of 250ms")
    else:
        target_seconds = args.target
    
    target_ms = target_seconds * 1000
    
    print(f"\n=== Performance Degradation Test ===")
    print(f"Target: {target_ms:.2f}ms ({device.upper()})")
    print(f"Base URL: {args.base_url}")
    print()
    
    # Run test
    latencies = run_latency_test(args.base_url, args.samples)
    
    # Analyze results
    success = analyze_results(latencies, target_ms, device)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
