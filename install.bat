@echo off
cd /d "%~dp0"
setlocal
echo Installing Azure Programming Language...

SET /P INSTALL_PATH="Enter install path (default: C:\Program Files\Azure): "
IF "%INSTALL_PATH%"=="" SET INSTALL_PATH=C:\Program Files\Azure

echo Installing to: %INSTALL_PATH%

CHOICE /C YN /M "Install clang?"
IF %ERRORLEVEL% EQU 1 GOTO INSTALL_CLANG
IF %ERRORLEVEL% EQU 2 GOTO SKIP_CLANG
:INSTALL_CLANG
echo Installing Clang...
winget install LLVM.LLVM --accept-source-agreements --accept-package-agreements
IF EXIST "C:\Program Files\LLVM\bin\clang.exe" (
    SET CLANG_DIR=C:\Program Files\LLVM\bin
    GOTO SKIP_CLANG
)
IF EXIST "C:\Program Files (x86)\LLVM\bin\clang.exe" (
    SET CLANG_DIR=C:\Program Files (x86)\LLVM\bin
    GOTO SKIP_CLANG
)
IF EXIST "%INSTALL_PATH%\LLVM\bin\clang.exe" (
    SET CLANG_DIR=%INSTALL_PATH%\LLVM\bin
    GOTO SKIP_CLANG
)
echo Could not find clang.exe, please add it to PATH manually
:SKIP_CLANG

CHOICE /C YN /M "Install python?"
IF %ERRORLEVEL% EQU 1 GOTO INSTALL_PYTHON
IF %ERRORLEVEL% EQU 2 GOTO SKIP_PYTHON
:INSTALL_PYTHON
echo Installing Python...
winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
:SKIP_PYTHON

echo Refreshing PATH...
call refreshenv 2>nul || (
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts"
)

CHOICE /C YN /M "Install LLVM(llvmlite)?"
IF %ERRORLEVEL% EQU 1 GOTO INSTALL_LLVM
IF %ERRORLEVEL% EQU 2 GOTO SKIP_LLVM
:INSTALL_LLVM
echo Installing llvmlite...
pip install llvmlite
:SKIP_LLVM

CHOICE /C YN /M "Bundle python scripts into executable?"
IF %ERRORLEVEL% EQU 1 GOTO BUNDLE
IF %ERRORLEVEL% EQU 2 GOTO SKIP_BUNDLE
:BUNDLE
echo Installing pyinstaller...
python -m pip install --user pyinstaller
echo Bundling python scripts...
python -m PyInstaller --onefile src/main.py
echo Creating environmental variable for Azure...
mkdir "%INSTALL_PATH%" 2>nul
copy "dist\main.exe" "%INSTALL_PATH%\azure.exe"
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path') do set "CURRENT_PATH=%%B"
setx Path "%CURRENT_PATH%;%INSTALL_PATH%" /M
echo Azure installed to: %INSTALL_PATH%
:SKIP_BUNDLE

echo.
echo Done! Please restart your terminal.
pause