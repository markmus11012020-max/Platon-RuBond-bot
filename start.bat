@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================================
REM  Platon-RuBond-bot Platform - start.bat
REM  Orchestration: stop -> clean cache -> venv + deps -> streamlit
REM ============================================================================

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "VENV_DIR=%ROOT%.venv"
set "PYTHON_VENV=%VENV_DIR%\Scripts\python.exe"
set "PIP_VENV=%VENV_DIR%\Scripts\pip.exe"
set "STREAMLIT_VENV=%VENV_DIR%\Scripts\streamlit.exe"
set "APP_FILE=app.py"
set "REQUIREMENTS=requirements.txt"
set "PORT=8501"
set "HOST=localhost"

echo.
echo ============================================================
echo   Platon-RuBond-bot Platform - deploy / start
echo ============================================================
echo   Root: %ROOT%
echo.

REM ---------- 1. Stop old processes ----------
echo [1/4] Stopping old processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$conn = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if ($conn) { $conn | ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }; Write-Host ('       Freed port %PORT%') }"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'streamlit|app\.py|platon_rubond' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('       Killed PID ' + $_.ProcessId) } catch {} }"
timeout /t 1 /nobreak >nul
echo       Done.
echo.

REM ---------- 2. Clear cache ----------
echo [2/4] Clearing cache...
if exist "%ROOT%__pycache__" rd /s /q "%ROOT%__pycache__" 2>nul
if exist "%ROOT%src\__pycache__" rd /s /q "%ROOT%src\__pycache__" 2>nul
for /d /r "%ROOT%src" %%D in (__pycache__) do (
    if exist "%%D" rd /s /q "%%D" 2>nul
)
if exist "%ROOT%.pytest_cache" rd /s /q "%ROOT%.pytest_cache" 2>nul
if exist "%ROOT%tool_cache.db" del /f /q "%ROOT%tool_cache.db" 2>nul
if exist "%ROOT%.streamlit\cache" rd /s /q "%ROOT%.streamlit\cache" 2>nul
del /s /q "%ROOT%*.pyc" >nul 2>&1
echo       Done.
echo.

REM ---------- 3. Environment + dependencies ----------
echo [3/4] Environment and dependencies...

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found in PATH. Install Python 3.10+ and retry.
    exit /b 1
)

if not exist "%PYTHON_VENV%" (
    echo       Creating venv: %VENV_DIR%
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: failed to create virtualenv.
        exit /b 1
    )
) else (
    echo       Using existing venv: %VENV_DIR%
)

echo       Upgrading pip...
"%PYTHON_VENV%" -m pip install --upgrade pip setuptools wheel -q
if errorlevel 1 (
    echo WARNING: pip upgrade failed, continuing...
)

if not exist "%ROOT%%REQUIREMENTS%" (
    echo ERROR: %REQUIREMENTS% not found.
    exit /b 1
)

echo       Installing requirements...
"%PIP_VENV%" install -r "%ROOT%%REQUIREMENTS%"
if errorlevel 1 (
    echo ERROR: dependency installation failed.
    exit /b 1
)

if not exist "%ROOT%.env" (
    if exist "%ROOT%.env.example" (
        echo       .env missing - copying from .env.example
        copy /Y "%ROOT%.env.example" "%ROOT%.env" >nul
        echo       Fill API keys in .env before production use.
    )
)

echo       Done.
echo.

REM ---------- 4. Start project ----------
echo [4/4] Starting Streamlit...
if not exist "%ROOT%%APP_FILE%" (
    echo ERROR: %APP_FILE% not found.
    exit /b 1
)

echo.
echo   URL:  http://%HOST%:%PORT%
echo   Stop: Ctrl+C  or  close this window
echo ============================================================
echo.

"%STREAMLIT_VENV%" run "%ROOT%%APP_FILE%" --server.port %PORT% --server.address %HOST% --browser.gatherUsageStats false

set "EXITCODE=%ERRORLEVEL%"
echo.
echo Streamlit exited with code %EXITCODE%
endlocal
exit /b %EXITCODE%
