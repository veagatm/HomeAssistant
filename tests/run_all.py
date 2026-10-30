"""
Test runner — runs all test_*.py files and reports pass/fail.

Usage:
    cd HomeAssistant/tests
    python3 run_all.py              # full suite
    python3 run_all.py health       # infrastructure health only (post-upgrade first step)
    python3 run_all.py motion tv    # specific modules
    python3 run_all.py cameras soil # camera + soil tests

Module reference:
    health    — entity registry, automation counts, helper existence (read-only)
    snooze    — snooze/clear_snooze script pair
    presence  — away mode, arriving home
    scripts   — good_night_all, set_trash_night, find phone
    cameras   — camera entity health, motion alert automations
    doors     — door contact sensors, arrival grace-period flags
    soil      — soil moisture sensors, alert automations
    motion    — motion sensor → light automations (injects MQTT)
    tv        — TV state → light dimming automations
    switch    — bedroom wall switch actions
    laundry   — washer/dryer vibration detection

Run order recommendation after an HA upgrade:
    1. python3 run_all.py health     (read-only — safe to run immediately)
    2. python3 run_all.py cameras soil snooze presence
    3. python3 run_all.py motion tv switch laundry  (these change light state)

Exit code: 0 if all pass, 1 if any fail.
"""

import importlib
import sys
import traceback

# health first: it's read-only and catches infrastructure regressions quickly
ALL_MODULES = [
    "test_health",
    "test_snooze",
    "test_presence",
    "test_scripts",
    "test_cameras",
    "test_doors",
    "test_soil",
    "test_motion",
    "test_tv",
    "test_switch",
    "test_laundry",
]


def run_module(mod_name: str) -> tuple[int, int]:
    passed, failed = 0, 0
    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:
        print(f"ERROR: Could not import {mod_name}: {e}")
        return 0, 1

    fns = [(name, fn) for name, fn in vars(mod).items()
           if name.startswith("test_") and callable(fn)]

    if not fns:
        print(f"  (no tests found in {mod_name})")
        return 0, 0

    for name, fn in fns:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {mod_name}.{name}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {mod_name}.{name}: {e}")
            traceback.print_exc()
            failed += 1

    return passed, failed


def main():
    if len(sys.argv) > 1:
        modules = [f"test_{arg}" if not arg.startswith("test_") else arg
                   for arg in sys.argv[1:]]
    else:
        modules = ALL_MODULES

    total_passed, total_failed = 0, 0
    for mod in modules:
        print(f"\n── {mod} ──")
        p, f = run_module(mod)
        total_passed += p
        total_failed += f

    print(f"\n{'='*40}")
    print(f"{total_passed} passed, {total_failed} failed")
    sys.exit(1 if total_failed else 0)


if __name__ == "__main__":
    main()
