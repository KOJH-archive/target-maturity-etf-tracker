import sqlite3
import os
import json
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tracker.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table 1: etf_master
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS etf_master (
        ticker TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        target_date TEXT NOT NULL,
        asset_class TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    );
    """)
    
    # Table 2: daily_etf_raw
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_etf_raw (
        date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        shares_outstanding INTEGER,
        nav REAL,
        aum INTEGER,
        PRIMARY KEY (date, ticker),
        FOREIGN KEY (ticker) REFERENCES etf_master(ticker)
    );
    """)
    
    # Table 3: duration_flow_daily
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS duration_flow_daily (
        date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        duration REAL,
        duration_bucket TEXT,
        net_shares_change INTEGER,
        net_fund_flow REAL,
        flow_ma3 REAL,
        flow_ma5 REAL,
        PRIMARY KEY (date, ticker),
        FOREIGN KEY (ticker) REFERENCES etf_master(ticker)
    );
    """)
    
    conn.commit()
    conn.close()
    print(f"[DB] Initialized SQLite Database at {DB_PATH}")

def sync_dynamic_universe(universe_list):
    """
    Dynamically sync the discovered ETF universe into the master table.
    universe_list is a list of dicts: [{'ticker':..., 'name':..., 'target_date':..., 'asset_class':...}, ...]
    """
    if not universe_list:
        print("[DB Warning] No dynamic ETFs provided to sync.")
        return
        
    conn = get_connection()
    cursor = conn.cursor()
    for item in universe_list:
        cursor.execute("""
        INSERT INTO etf_master (ticker, name, target_date, asset_class, is_active)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(ticker) DO UPDATE SET
            name=excluded.name,
            target_date=excluded.target_date,
            asset_class=excluded.asset_class,
            is_active=1;
        """, (item['ticker'], item['name'], item['target_date'], item['asset_class']))
        
    conn.commit()
    conn.close()
    print(f"[DB] Synced {len(universe_list)} dynamically discovered ETFs into etf_master.")

def load_etf_master(active_only=True):
    conn = get_connection()
    query = "SELECT * FROM etf_master"
    if active_only:
        query += " WHERE is_active = 1"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def save_daily_raw(df_raw):
    if df_raw.empty:
        return
    conn = get_connection()
    cursor = conn.cursor()
    for _, row in df_raw.iterrows():
        cursor.execute("""
        INSERT INTO daily_etf_raw (date, ticker, shares_outstanding, nav, aum)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date, ticker) DO UPDATE SET
            shares_outstanding=excluded.shares_outstanding,
            nav=excluded.nav,
            aum=excluded.aum;
        """, (str(row['date']), str(row['ticker']), int(row['shares_outstanding']), float(row['nav']), int(row.get('aum', 0))))
    conn.commit()
    conn.close()

def save_duration_flow(df_flow):
    if df_flow.empty:
        return
    conn = get_connection()
    cursor = conn.cursor()
    for _, row in df_flow.iterrows():
        cursor.execute("""
        INSERT INTO duration_flow_daily (date, ticker, duration, duration_bucket, net_shares_change, net_fund_flow, flow_ma3, flow_ma5)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, ticker) DO UPDATE SET
            duration=excluded.duration,
            duration_bucket=excluded.duration_bucket,
            net_shares_change=excluded.net_shares_change,
            net_fund_flow=excluded.net_fund_flow,
            flow_ma3=excluded.flow_ma3,
            flow_ma5=excluded.flow_ma5;
        """, (
            str(row['date']),
            str(row['ticker']),
            float(row['duration']),
            str(row['duration_bucket']),
            int(row['net_shares_change']),
            float(row['net_fund_flow']),
            float(row['flow_ma3']) if pd.notnull(row['flow_ma3']) else None,
            float(row['flow_ma5']) if pd.notnull(row['flow_ma5']) else None
        ))
    conn.commit()
    conn.close()

def get_combined_flow_data():
    conn = get_connection()
    query = """
    SELECT 
        f.date,
        f.ticker,
        m.name,
        m.asset_class,
        m.target_date,
        f.duration,
        f.duration_bucket,
        f.net_shares_change,
        f.net_fund_flow,
        f.flow_ma3,
        f.flow_ma5,
        r.shares_outstanding,
        r.nav,
        r.aum
    FROM duration_flow_daily f
    JOIN etf_master m ON f.ticker = m.ticker
    LEFT JOIN daily_etf_raw r ON f.date = r.date AND f.ticker = r.ticker
    ORDER BY f.date ASC, f.ticker ASC;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

if __name__ == "__main__":
    init_db()
    sync_etf_universe()
