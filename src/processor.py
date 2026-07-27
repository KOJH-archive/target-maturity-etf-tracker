import datetime
import pandas as pd
import numpy as np

from src.db_manager import get_connection, load_etf_master, save_duration_flow

def get_duration_bucket(duration_years):
    if duration_years <= 0.5:
        return "0.5Y 이하"
    elif duration_years <= 1.0:
        return "1.0Y 구간"
    elif duration_years <= 1.5:
        return "1.5Y 구간"
    else:
        return "2.0Y 이상"

def calculate_duration(current_date_str, target_date_str):
    curr = pd.to_datetime(current_date_str)
    targ = pd.to_datetime(target_date_str)
    days_diff = (targ - curr).days
    duration = days_diff / 365.25
    return max(0.0, round(duration, 4))

def process_fund_flow_and_duration():
    conn = get_connection()
    raw_df = pd.read_sql("SELECT * FROM daily_etf_raw ORDER BY ticker, date ASC", conn)
    master_df = load_etf_master(active_only=True)
    conn.close()

    if raw_df.empty or master_df.empty:
        print("[Processor Warning] Raw data or master data is empty.")
        return pd.DataFrame()

    # Merge target_date from master
    merged = pd.merge(raw_df, master_df[['ticker', 'target_date']], on='ticker', how='inner')
    merged['date'] = pd.to_datetime(merged['date'])
    merged = merged.sort_values(by=['ticker', 'date']).reset_index(drop=True)

    processed_rows = []

    for ticker, group in merged.groupby('ticker'):
        group = group.sort_values('date').copy()
        
        # Calculate lag NAV and lag Shares
        group['prev_shares'] = group['shares_outstanding'].shift(1)
        group['prev_nav'] = group['nav'].shift(1)

        for i, row in group.iterrows():
            curr_date_str = row['date'].strftime('%Y-%m-%d')
            target_date_str = str(row['target_date'])
            
            # Duration & Bucket
            dur = calculate_duration(curr_date_str, target_date_str)
            bucket = get_duration_bucket(dur)

            # Net Shares Change & Net Fund Flow
            if pd.isna(row['prev_shares']) or pd.isna(row['prev_nav']):
                net_shares_change = 0
                net_fund_flow = 0.0
            else:
                net_shares_change = int(row['shares_outstanding'] - row['prev_shares'])
                # Net Fund Flow = (Shares_t - Shares_t-1) * NAV_t-1
                net_fund_flow = float(net_shares_change * row['prev_nav'])

            processed_rows.append({
                'date': curr_date_str,
                'ticker': ticker,
                'duration': dur,
                'duration_bucket': bucket,
                'net_shares_change': net_shares_change,
                'net_fund_flow': net_fund_flow
            })

    result_df = pd.DataFrame(processed_rows)
    if result_df.empty:
        return result_df

    # Sort and calculate Moving Averages (MA3, MA5) per ticker
    result_df['date'] = pd.to_datetime(result_df['date'])
    result_df = result_df.sort_values(['ticker', 'date']).reset_index(drop=True)

    result_df['flow_ma3'] = result_df.groupby('ticker')['net_fund_flow'].transform(
        lambda x: x.rolling(window=3, min_periods=1).mean()
    )
    result_df['flow_ma5'] = result_df.groupby('ticker')['net_fund_flow'].transform(
        lambda x: x.rolling(window=5, min_periods=1).mean()
    )

    result_df['date'] = result_df['date'].dt.strftime('%Y-%m-%d')

    # Save to SQLite
    save_duration_flow(result_df)
    print(f"[Processor] Successfully processed and saved {len(result_df)} duration flow daily records.")
    return result_df

if __name__ == "__main__":
    process_fund_flow_and_duration()
