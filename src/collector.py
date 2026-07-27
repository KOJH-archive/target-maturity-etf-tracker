import datetime
import time
import requests
import re
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup

from src.db_manager import load_etf_master, save_daily_raw, sync_dynamic_universe

def fetch_etf_live_naver():
    """
    Fetch current live ETF metrics for all ETFs from Naver Finance ETF API.
    Returns dict mapping ticker to live data dict including the item name.
    """
    url = "https://finance.naver.com/api/sise/etfItemList.nhn"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    live_map = {}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            items = data.get('result', {}).get('etfItemList', [])
            for item in items:
                ticker = str(item.get('itemcode'))
                name = str(item.get('itemname', ''))
                nav = float(item.get('nav', 0))
                market_sum_eok = float(item.get('marketSum', 0))
                aum = int(market_sum_eok * 100_000_000)
                shares = int(aum / nav) if nav > 0 else 0
                
                live_map[ticker] = {
                    'name': name,
                    'nav': nav,
                    'aum': aum,
                    'shares_outstanding': shares
                }
    except Exception as e:
        print(f"[Collector Naver API Error]: {e}")
    return live_map

def discover_maturity_matching_etfs(live_map):
    """
    Scans the entire live_map for ETFs that have YY-MM target dates in their names.
    Returns a list of dicts suitable for db_manager.sync_dynamic_universe.
    """
    discovered = []
    # Match patterns like "26-12", "27-04" indicating target maturity year and month
    pattern = re.compile(r'(\d{2})-(\d{2})')
    
    for ticker, data in live_map.items():
        name = data.get('name', '')
        match = pattern.search(name)
        if match:
            yy, mm = match.groups()
            # Convert 2-digit year to 4-digit and set day to 15th for duration calc
            target_date = f"20{yy}-{mm}-15"
            
            # Simple keyword matching for asset class based on standard ETF names
            if '회사채' in name:
                asset_class = '회사채'
            elif '은행채' in name:
                asset_class = '은행채'
            elif '국고채' in name:
                asset_class = '국고채'
            elif '특수채' in name:
                asset_class = '특수채'
            else:
                asset_class = '기타채권'
                
            discovered.append({
                'ticker': ticker,
                'name': name,
                'target_date': target_date,
                'asset_class': asset_class,
                'aum': data.get('aum', 0)
            })
            
    return discovered

def fetch_etf_chart_naver(ticker, count=40):
    """
    Fetch daily price/volume chart history from Naver Chart API.
    """
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={ticker}&timeframe=day&count={count}&requestType=0"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/120.0.0.0'
    }
    records = []
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            items = root.findall('.//item')
            for item in items:
                # Format: YYYYMMDD|Open|High|Low|Close|Volume
                data_str = item.attrib.get('data', '')
                parts = data_str.split('|')
                if len(parts) >= 6:
                    date_str = parts[0]
                    close_price = float(parts[4])
                    records.append({
                        'date': f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                        'ticker': str(ticker),
                        'close': close_price
                    })
    except Exception as e:
        print(f"[Collector Naver Chart Error] Ticker {ticker}: {e}")
    return pd.DataFrame(records)

def collect_historical_data(days_back=30):
    """
    Dynamically discover maturity-matching ETFs, pick the Top 10 by AUM,
    sync to DB, and collect real market data.
    """
    print(f"[Collector] Fetching live market data for ALL 1,100+ ETFs from Naver Finance...")
    live_map = fetch_etf_live_naver()
    
    # 1. Dynamically discover all target maturity ETFs via RegEx
    discovered_list = discover_maturity_matching_etfs(live_map)
    print(f"[Collector] Dynamically discovered {len(discovered_list)} maturity-matching ETFs in the market.")
    
    if not discovered_list:
        print("[Collector] Error: No maturity-matching ETFs found.")
        return pd.DataFrame()

    # 2. Sort by AUM and pick top 10
    discovered_list.sort(key=lambda x: x['aum'], reverse=True)
    top_10 = discovered_list[:10]
    top_tickers = [x['ticker'] for x in top_10]
    print(f"[Collector] Selected top-10 by AUM: {', '.join(sorted(top_tickers))}")
    
    # 3. Sync dynamic universe to DB
    sync_dynamic_universe(top_10)
    
    # 4. Iterate over top 10 and fetch chart data
    master_df = pd.DataFrame(top_10)
    all_dfs = []
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    for _, row in master_df.iterrows():
        ticker = str(row['ticker'])
        name = row['name']
        print(f" -> Fetching real market series for {name} ({ticker})...")
        
        chart_df = fetch_etf_chart_naver(ticker, count=days_back)
        
        live_info = live_map.get(ticker, {})
        base_nav = live_info.get('nav', 10000.0)
        base_shares = live_info.get('shares_outstanding', 1000000)
        base_aum = live_info.get('aum', int(base_shares * base_nav))

        if not chart_df.empty:
            # Use daily price ratio to NAV for real daily estimates
            latest_close = chart_df.iloc[-1]['close'] if not chart_df.empty and chart_df.iloc[-1]['close'] > 0 else base_nav
            
            chart_df['nav'] = (chart_df['close'] / latest_close) * base_nav
            chart_df['shares_outstanding'] = base_shares
            chart_df['aum'] = base_aum
            
            df_final = chart_df[['date', 'ticker', 'shares_outstanding', 'nav', 'aum']].copy()
            
            if live_info and today_str not in df_final['date'].values:
                today_row = pd.DataFrame([{
                    'date': today_str,
                    'ticker': ticker,
                    'shares_outstanding': base_shares,
                    'nav': base_nav,
                    'aum': base_aum
                }])
                df_final = pd.concat([df_final, today_row], ignore_index=True)

            print(f"    [SUCCESS] Loaded {len(df_final)} real daily market records.")
            all_dfs.append(df_final)
        else:
            print(f"    [WARNING] No chart history for {ticker}")
            
        time.sleep(0.2)
        
    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=['date', 'ticker'])
        save_daily_raw(combined_df)
        print(f"[Collector] Successfully stored {len(combined_df)} real market records in SQLite DB.")
        return combined_df
    else:
        print("[Collector] Warning: No data collected.")
        return pd.DataFrame()

if __name__ == "__main__":
    collect_historical_data(days_back=30)
