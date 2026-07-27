# Target‑Maturity ETF Tracker (Dynamic Discovery)

**Fully automated** tracker that discovers **all** Korean target‑maturity (만기매칭형) bond ETFs in real‑time, stores daily NAV/AUM data in a local SQLite DB, computes **real net fund‑flow** and **duration buckets**, and visualizes the results in an interactive Streamlit dashboard.

---

## 🛠️ Core Features (현재 구현된 주요 기능)

1. **Dynamic ETF Universe Discovery**
   - At each run, the collector calls Naver Finance (`etfItemList.nhn`) to fetch **the entire list of ~1,150 ETFs**.
   - A regex (`\d{2}-\d{2}`) extracts the target year‑month from the fund name, automatically selecting **all** maturity‑matching ETFs **without any hard‑coded JSON file**.
   - From the discovered set, the **top‑10 by AUM** are selected and up‑serted into `etf_master`.
2. **Live Market Data Capture**
   - For the selected 10 ETFs, daily price history is retrieved via Naver chart API.
   - Current NAV, shares outstanding, and AUM are combined with historical prices to produce a clean daily dataset.
3. **Net Fund‑Flow & Duration Calculation**
   - Net Flow: `(Shares_t - Shares_{t‑1}) × NAV_{t‑1}`
   - Duration: `(TargetDate - CurrentDate) / 365.25`
   - Bucketing into `0‑0.5Y`, `0.5‑1.0Y`, `1.0‑1.5Y`, `>1.5Y` for macro analysis.
4. **Streamlit Dashboard**
   - Dark‑mode UI with Plotly charts.
   - Sidebar filters for **date range**, **sorting (AUM / shortest‑maturity / longest‑maturity)**, and **asset class**.
   - Real‑time cumulative net‑flow updates when the period selection changes.
5. **Windows Task Scheduler Automation**
   - `setup_task_scheduler.bat` registers a daily task (`ETF_FundFlow_Tracker`) that runs at **16:00** and silently executes `run_daily_sync.bat` (collector + processor).
   - No manual batch execution required after the one‑time registration.

---

## 📂 Project Structure

```text
c:/Users/Check/Downloads/만기매칭형 ETF/
├── data/
│   └── tracker.db                 # SQLite DB (auto‑created)
├── src/
│   ├── __init__.py
│   ├── db_manager.py              # DB schema & UPSERT sync
│   ├── collector.py               # Dynamic discovery & daily raw import
│   └── processor.py               # Fund‑flow & duration calculations
├── app.py                         # Streamlit dashboard
├── requirements.txt               # Python dependencies
├── run_daily_sync.bat             # Headless execution script
├── run_tracker.bat                # Launches Streamlit UI
├── setup_task_scheduler.bat       # Registers Windows scheduled task
└── README.md                     # (this file)
```

---

## 🚀 Getting Started

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Initial DB setup & first data pull**
   ```bash
   python -m src.db_manager   # creates tables
   python -m src.collector    # discovers ETFs & stores daily raw data
   python -m src.processor    # calculates fund‑flow & duration
   ```
3. **Run the dashboard**
   ```bash
   streamlit run app.py
   ```
4. **(Optional) Automate daily collection**
   ```bash
   setup_task_scheduler.bat   # registers the 16:00 daily task
   ```

---

## 📊 What You See on the Dashboard

- **ETF table** showing ticker, name, target date, current AUM, and latest NAV.
- **Duration‑bucket chart** with cumulative net‑flow (blue = inflow, red = outflow).
- **Date‑range selector** – the cumulative figure updates instantly, reflecting exactly the period you choose.

---

## 📌 Future Enhancements (planned)

- Credit‑spread integration (K‑Bond API) for correlation analysis.
- Institution / foreign investor net‑position parsing.
- Multi‑year historical back‑fill (once the market data becomes available).

---

## 📜 License

MIT License – feel free to fork, adapt, and contribute!
