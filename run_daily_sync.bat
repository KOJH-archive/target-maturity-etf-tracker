@echo off
echo ===================================================
echo ETF Background Daily Data Sync
echo ===================================================
echo.
echo [1/2] Fetching Live Market Data (Naver Finance)...
py -3 -m src.collector
echo.
echo [2/2] Processing Fund Flow and Duration...
py -3 -m src.processor
echo.
echo Daily Sync Completed.
