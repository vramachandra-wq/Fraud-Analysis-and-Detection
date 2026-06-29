@echo off
cd /d "%~dp0"

echo Starting containers...
py -m podman_compose up -d

echo.
echo Waiting for OLTP database...
:oltp
for /f %%i in ('podman inspect oltp_db --format "{{.State.Health.Status}}"') do set STATUS=%%i
if not "%STATUS%"=="healthy" (
    timeout /t 2 >nul
    goto oltp
)

echo Waiting for OLAP database...
:olap
for /f %%i in ('podman inspect olap_db --format "{{.State.Health.Status}}"') do set STATUS=%%i
if not "%STATUS%"=="healthy" (
    timeout /t 2 >nul
    goto olap
)

echo Waiting for Zookeeper...
:zookeeper
for /f %%i in ('podman inspect zookeeper --format "{{.State.Health.Status}}"') do set STATUS=%%i
if not "%STATUS%"=="healthy" (
    timeout /t 2 >nul
    goto zookeeper
)

echo Waiting for Kafka...
:kafka
for /f %%i in ('podman inspect kafka --format "{{.State.Health.Status}}"') do set STATUS=%%i
if not "%STATUS%"=="healthy" (
    timeout /t 2 >nul
    goto kafka
)

echo Waiting for Debezium...
:debezium
for /f %%i in ('podman inspect debezium --format "{{.State.Health.Status}}"') do set STATUS=%%i
if not "%STATUS%"=="healthy" (
    timeout /t 2 >nul
    goto debezium
)

echo Waiting for Superset...
:superset
for /f %%i in ('podman inspect superset --format "{{.State.Health.Status}}"') do set STATUS=%%i
if not "%STATUS%"=="healthy" (
    timeout /t 5 >nul
    goto superset
)

echo Waiting for Airflow Webserver...
:airflow
for /f %%i in ('podman inspect airflow_webserver --format "{{.State.Health.Status}}"') do set STATUS=%%i
if not "%STATUS%"=="healthy" (
    timeout /t 5 >nul
    goto airflow
)

echo.
echo All services are healthy.
echo Starting Streamlit...

start "Streamlit" cmd /c "call .venv\Scripts\activate.bat && streamlit run app.py"

echo Application started successfully.
pause