@echo off
echo ===================================================
echo ETF Fund Flow Tracker Launcher
echo ===================================================
echo.
echo [1/3] Fetching Live Market Data (Naver Finance)...
py -3 -m src.collector
echo.
echo [2/3] Processing Fund Flow and Duration...
py -3 -m src.processor
echo.
echo [3/3] Launching Dashboard in Browser...
py -3 -m streamlit run app.py
pause
