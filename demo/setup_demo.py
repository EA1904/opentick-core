"""
OpenTick — Demo Setup Script
============================
Sets up a minimal working demo with NVDA (NVIDIA) daily price data (2015→2026).
No API keys needed. No ingestion required. Ready in ~5 seconds.

Usage:
    python setup_demo.py
    uvicorn data_explorer:app --host 0.0.0.0 --port 8001 --reload
    # Open http://localhost:8001 → select NVDA → explore!
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.join(ROOT, "demo")
LAKE_DST = os.path.join(ROOT, "lake")
CATALOG_DST = os.path.join(ROOT, "catalog.db")


def main():
    print("=" * 55)
    print("  OpenTick — Demo Setup")
    print("=" * 55)

    # ── Check demo folder exists ─────────────────────────────
    demo_lake = os.path.join(DEMO_DIR, "lake")
    demo_catalog = os.path.join(DEMO_DIR, "catalog.db")

    if not os.path.exists(demo_lake) or not os.path.exists(demo_catalog):
        print("❌  Demo data not found in demo/ folder.")
        print("   Please make sure you cloned the full repository.")
        sys.exit(1)

    # ── Warn if real data would be overwritten ───────────────
    if os.path.exists(CATALOG_DST):
        ans = input(
            "\n⚠️  A catalog.db already exists. Overwrite with demo data? [y/N] "
        ).strip().lower()
        if ans != "y":
            print("Aborted. Your existing catalog.db was not modified.")
            sys.exit(0)

    # ── Copy demo lake → lake/ ───────────────────────────────
    print("\n[1/2] Copying demo Parquet data (NVDA D1 2015→2026)...")
    nvda_dst = os.path.join(
        LAKE_DST,
        "ohlcv",
        "asset_class=stocks",
        "timeframe=D1",
        "symbol=NVDA",
    )
    nvda_src = os.path.join(
        demo_lake,
        "ohlcv",
        "asset_class=stocks",
        "timeframe=D1",
        "symbol=NVDA",
    )
    if os.path.exists(nvda_dst):
        shutil.rmtree(nvda_dst)
    shutil.copytree(nvda_src, nvda_dst)
    size = sum(
        os.path.getsize(os.path.join(r, f))
        for r, d, files in os.walk(nvda_dst)
        for f in files
    )
    print(f"   ✅  NVDA data copied ({size / 1024:.0f} KB, 2,926 daily bars)")

    # ── Copy demo catalog.db ─────────────────────────────────
    print("[2/2] Installing demo catalog.db...")
    shutil.copy2(demo_catalog, CATALOG_DST)
    print("   ✅  catalog.db ready")

    # ── Done ─────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  ✅  Demo setup complete!")
    print("=" * 55)
    print("\nNext steps:")
    print("  pip install -r requirements.txt")
    print("  uvicorn data_explorer:app --host 0.0.0.0 --port 8001 --reload")
    print("  → Open http://localhost:8001")
    print("  → Select NVDA — 2,926 daily bars (2015–2026) ready to explore!")
    print()
    print("For the full dataset (530+ symbols, fundamentals, macro, options):")
    print("  → See README.md › Data Ingestion section")
    print("  → Or contact us for curated dataset access")
    print()


if __name__ == "__main__":
    main()
