#!/usr/bin/env python3
"""
Comprehensive overnight test suite for all new modules
"""

import subprocess
import sys

def run_test(name, command):
    """Run a test and report results."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    
    result = subprocess.run(command, shell=True, cwd="/Users/12-mac-alpha/Projects/inkclone")
    
    if result.returncode == 0:
        print(f"✅ PASSED: {name}")
        return True
    else:
        print(f"❌ FAILED: {name}")
        return False

def main():
    print("\n" + "="*60)
    print("INKCLONE OVERNIGHT TEST SUITE")
    print("="*60)
    
    tests = [
        ("Template Generator v2", "python3 template_generator_v2.py"),
        ("Natural Writing Analyzer", "python3 natural_writing_analyzer.py"),
        ("Paper Backgrounds (with new types)", "python3 paper_backgrounds.py"),
        ("Ink Effects", "python3 ink_effects.py"),
        ("Page Layout Engine", "python3 page_layout.py"),
        ("Existing Test Suite", "python3 -m pytest test_all.py -v"),
    ]
    
    results = {}
    for name, command in tests:
        results[name] = run_test(name, command)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
