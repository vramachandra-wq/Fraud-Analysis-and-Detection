@echo off
cd /d "%~dp0"

echo Stopping Streamlit...
taskkill /F /FI "WINDOWTITLE eq Streamlit*" >nul 2>&1

echo Stopping containers...
py -m podman_compose down

echo.
echo All services stopped.
pause