@echo off
REM DJ Music Library Cleanup Tool - Windows Launcher
REM This script helps run the cleanup tool on Windows

echo ========================================
echo DJ Music Library Cleanup Tool
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if dependencies are installed
pip show pyacoustid >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    echo.
)

REM Check if fpcalc is available
fpcalc -version >nul 2>&1
if errorlevel 1 (
    echo WARNING: fpcalc (Chromaprint) not found in PATH
    echo Please install Chromaprint from: https://acoustid.org/chromaprint
    echo.
)

REM Display menu
:menu
echo What would you like to do?
echo.
echo 1. Create configuration file (first time setup)
echo 2. Analyze library only (no changes)
echo 3. Preview changes (dry run)
echo 4. Execute cleanup
echo 5. Resume previous cleanup
echo 6. Exit
echo.

set /p choice="Enter your choice (1-6): "

if "%choice%"=="1" (
    echo.
    echo Creating example configuration file...
    python music_cleanup.py --create-config
    echo.
    echo Please edit example_config.json with your folder paths
    pause
    goto menu
)

if "%choice%"=="2" (
    echo.
    python music_cleanup.py --scan-only
    pause
    goto menu
)

if "%choice%"=="3" (
    echo.
    set /p config="Enter config file name (or press Enter for default): "
    if "%config%"=="" set config=music_cleanup_config.json
    python music_cleanup.py --dry-run --config "%config%"
    pause
    goto menu
)

if "%choice%"=="4" (
    echo.
    set /p config="Enter config file name (or press Enter for default): "
    if "%config%"=="" set config=music_cleanup_config.json
    echo.
    echo WARNING: This will copy and organize your music files.
    echo Protected folders will not be modified.
    echo Original files will not be deleted.
    echo.
    set /p confirm="Are you sure you want to continue? (yes/no): "
    if /i "%confirm%"=="yes" (
        python music_cleanup.py --execute --config "%config%"
    ) else (
        echo Operation cancelled.
    )
    pause
    goto menu
)

if "%choice%"=="5" (
    echo.
    python music_cleanup.py --execute --resume
    pause
    goto menu
)

if "%choice%"=="6" (
    echo.
    echo Goodbye!
    exit /b 0
)

echo Invalid choice. Please try again.
echo.
goto menu