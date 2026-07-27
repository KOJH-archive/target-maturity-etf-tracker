@echo off
echo ===================================================
echo ETF Auto-Sync Task Scheduler Setup
echo ===================================================
echo.
echo Registering daily task at 16:00 (4:00 PM)...
echo.

schtasks /create /tn "ETF_FundFlow_Tracker" /tr "\"%~dp0run_daily_sync.bat\"" /sc daily /st 16:00 /f

echo.
echo Setup Complete! The data will sync automatically everyday at 16:00.
pause
