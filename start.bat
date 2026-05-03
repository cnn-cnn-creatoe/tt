@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "HOST=127.0.0.1"
set "PORT=5000"
set "APP_URL=http://127.0.0.1:5000"
set "RUNTIME_DIR=%ROOT%\.runtime"
set "LOG_DIR=%ROOT%\logs"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%ROOT%\data" mkdir "%ROOT%\data"

if not exist "%ROOT%\config.json" if exist "%ROOT%\config.example.json" (
    copy "%ROOT%\config.example.json" "%ROOT%\config.json" >nul
)

call :find_python
if not defined PYTHON_CMD (
    call :install_python
    call :find_python
)

if not defined PYTHON_CMD (
    echo [ERROR] Python was not found and automatic installation failed.
    echo Please install Python 3.10 or newer, then run start.bat again.
    pause
    exit /b 1
)

if not exist "%VENV_PY%" (
    echo [INFO] Creating virtual environment...
    "%PYTHON_CMD%" -m venv "%ROOT%\.venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

"%VENV_PY%" -c "import flask, requests, openai" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing project dependencies...
    "%VENV_PY%" -m pip install --upgrade pip > "%LOG_DIR%\install.log" 2>&1
    "%VENV_PY%" -m pip install -r "%ROOT%\requirements.txt" >> "%LOG_DIR%\install.log" 2>&1
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. See logs\install.log.
        pause
        exit /b 1
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\start_service.ps1" -ProjectDir "%ROOT%" -PythonPath "%VENV_PY%" -HostName "%HOST%" -Port %PORT%
if errorlevel 1 (
    echo [ERROR] Service startup failed.
    pause
    exit /b 1
)

start "" "%APP_URL%"
exit /b 0

:find_python
set "PYTHON_CMD="
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python313\python.exe"
if defined PYTHON_CMD exit /b 0
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"
if defined PYTHON_CMD exit /b 0
where py >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_CMD=%%P"
    if defined PYTHON_CMD exit /b 0
)
where python >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_CMD=%%P"
    if defined PYTHON_CMD exit /b 0
)
exit /b 0

:install_python
where winget >nul 2>&1
if errorlevel 1 exit /b 0
echo [INFO] Python was not found. Trying to install Python 3.12 with winget...
winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
exit /b 0
