"""Local Senate eFD fetch test — run from your Mac (residential IP) to verify
the Playwright provider clears the WAF. Datacenter/CI IPs will still 403.

Usage:
    cd /Users/nikolassapalidis/sapa_fund
    uv run python scripts/test_senate_local.py
"""
import os
import sys

# Make the repo root importable when run as `python scripts/test_senate_local.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from equities.data.senate_efd_disclosures import SenateEFDDisclosureProvider


def main() -> None:
    provider = SenateEFDDisclosureProvider(
        max_reports=5,
        lookback_days=90,
        headless=False,  # headful passes Akamai's bot-check; a Chromium window will pop up
    )
    result = provider.fetch()

    print(f"source : {result.source}")
    print(f"trades : {len(result.trades)}")
    print(f"error  : {result.error}")
    print("-" * 60)
    for t in result.trades[:15]:
        print(f"  {t.date_filed}  {t.politician:24}  {t.ticker:6}  {t.transaction_type}")

    if result.trades:
        print("\nSUCCESS — WAF cleared from this IP, Senate data is flowing.")
    elif result.error:
        print("\nNo trades. If this is a 403, the IP is WAF-blocked (try residential).")


if __name__ == "__main__":
    main()
