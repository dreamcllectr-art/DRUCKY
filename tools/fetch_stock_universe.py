"""Fetch Russell 1000 constituents (S&P 500 + S&P 400 mid-caps) from Wikipedia."""

import io
import requests
import pandas as pd
from tools.db import init_db, upsert_many

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DruckenmillerAlpha/1.0)"}


def _read_html_ssl(url):
    """Read HTML tables via requests (bypasses SSL cert issue + Wikipedia 403)."""
    resp = requests.get(url, headers=_HEADERS, verify=False, timeout=20)
    resp.raise_for_status()
    return pd.read_html(io.StringIO(resp.text))


def fetch_sp500():
    """Scrape S&P 500 constituents from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = _read_html_ssl(url)
    df = tables[0]
    df = df.rename(columns={
        "Symbol": "symbol",
        "Security": "name",
        "GICS Sector": "sector",
        "GICS Sub-Industry": "industry",
    })
    df["symbol"] = df["symbol"].str.replace(".", "-", regex=False)
    return df[["symbol", "name", "sector", "industry"]]


def fetch_sp400():
    """Scrape S&P 400 mid-cap constituents from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    try:
        tables = _read_html_ssl(url)
        df = tables[0]
        col_map = {}
        for col in df.columns:
            cl = col.lower()
            if "symbol" in cl or "ticker" in cl:
                col_map[col] = "symbol"
            elif "company" in cl or "security" in cl or "name" in cl:
                col_map[col] = "name"
            elif "sector" in cl:
                col_map[col] = "sector"
            elif "industry" in cl or "sub" in cl:
                col_map[col] = "industry"
        df = df.rename(columns=col_map)
        if "symbol" not in df.columns:
            return pd.DataFrame(columns=["symbol", "name", "sector", "industry"])
        df["symbol"] = df["symbol"].str.replace(".", "-", regex=False)
        for col in ["name", "sector", "industry"]:
            if col not in df.columns:
                df[col] = ""
        return df[["symbol", "name", "sector", "industry"]]
    except Exception as e:
        print(f"Warning: Could not fetch S&P 400: {e}")
        return pd.DataFrame(columns=["symbol", "name", "sector", "industry"])


def run():
    """Fetch and store stock universe."""
    init_db()

    print("Fetching S&P 500 constituents...")
    sp500 = fetch_sp500()
    print(f"  Got {len(sp500)} S&P 500 stocks")

    print("Fetching S&P 400 mid-cap constituents...")
    sp400 = fetch_sp400()
    print(f"  Got {len(sp400)} S&P 400 stocks")

    universe = pd.concat([sp500, sp400], ignore_index=True).drop_duplicates(subset="symbol")
    print(f"  Total universe: {len(universe)} stocks")

    rows = [
        (row["symbol"], row["name"], row["sector"], row["industry"], None)
        for _, row in universe.iterrows()
    ]
    upsert_many("stock_universe", ["symbol", "name", "sector", "industry", "market_cap"], rows)
    print("Stock universe saved to database.")
    return universe


if __name__ == "__main__":
    run()
