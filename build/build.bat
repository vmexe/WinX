@echo off
setlocal
REM ---------------------------------------------------------------------------
REM Build WinX.exe on Windows.
REM
REM   build\build.bat            one-file GUI executable in dist\
REM   build\build.bat --clean    remove build caches first
REM ---------------------------------------------------------------------------
pushd "%~dp0.."

echo [1/4] Creating the virtual environment...
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller>=6.3

echo [3/4] Running the self-test...
python main.py --selftest
if errorlevel 1 (
    echo Self-test failed - aborting build.
    popd & exit /b 1
)

echo [4/4] Building with PyInstaller...
if "%1"=="--clean" (
    if exist build\WinX rmdir /s /q build\WinX
    if exist dist rmdir /s /q dist
)
pyinstaller build\WinX.spec --noconfirm

echo.
echo Done: dist\WinX.exe
popd
endlocal
