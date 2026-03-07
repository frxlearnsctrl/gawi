@echo off
setlocal
echo ======================================================
echo           GAWI - Dependency Installer
echo ======================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on this system.
    echo.
    echo Please install Python 3.x from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b
)

echo [OK] Python detected.
echo.

:: Upgrade pip first
echo [1/3] Checking for pip updates...
python -m pip install --upgrade pip --user

:: Install Gawi requirements
echo [2/3] Installing pystray (System Tray functionality)...
python -m pip install pystray --user

echo [3/3] Installing Pillow (Dynamic Icon generation)...
python -m pip install Pillow --user

echo.
echo ======================================================
echo Setup Complete!
echo You can now run the application using: gawi.pyw
echo ======================================================
echo.
pause
