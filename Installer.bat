@echo off
setlocal
title TinySDR installer

rem ---- settings (edit if you like) ----
set "INSTALL=C:\TinySDR"
set "BLOG_URL=https://github.com/rtlsdrblog/rtl-sdr-blog/releases/latest/download/Release.zip"
rem -------------------------------------

cd /d "%~dp0"
echo.
echo === TinySDR installer ===
echo.

if not exist "tinysdr.py" (
    echo ERROR: tinysdr.py must be in the same folder as this installer.
    goto fail
)
if not exist "tinysdr.bat" (
    echo ERROR: tinysdr.bat must be in the same folder as this installer.
    goto fail
)

rem ---------- 1. Python ----------
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" in the installer, then run this again.
    goto fail
)
python --version

rem ---------- 2. Python packages ----------
echo.
echo [2/5] Installing Python packages, this can take a minute...
python -m pip install --disable-pip-version-check pyrtlsdr==0.5.1 numpy scipy sounddevice libusb-package
if errorlevel 1 (
    echo pip failed. Check your internet connection and the messages above, then try again.
    goto fail
)

rem ---------- 3. Driver DLLs ----------
echo.
echo [3/5] Installing the RTL-SDR Blog driver DLLs...
set "SITE="
for /f "tokens=1,* delims= " %%A in ('python -m pip show pyrtlsdr ^| findstr /b /c:"Location:"') do set "SITE=%%B"
if not defined SITE (
    echo Could not locate the pyrtlsdr package folder.
    goto fail
)
set "PKG=%SITE%\rtlsdr"
if not exist "%PKG%" (
    echo Package folder not found: %PKG%
    goto fail
)

rem Use a Release.zip sitting next to this installer if there is one, otherwise download it
set "ZIP=%~dp0Release.zip"
if exist "%ZIP%" goto haveZip
set "ZIP=%TEMP%\rtlsdr-blog-Release.zip"
echo Downloading %BLOG_URL%
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -UseBasicParsing '%BLOG_URL%' -OutFile '%ZIP%' } catch { exit 1 }"
if errorlevel 1 goto dlfail
:haveZip

set "EX=%TEMP%\rtlsdr-blog-extract"
if exist "%EX%" rmdir /s /q "%EX%"
powershell -NoProfile -Command "Expand-Archive -Force -LiteralPath '%ZIP%' -DestinationPath '%EX%'"
if errorlevel 1 goto dlfail

set "BLOGDLL="
for /f "delims=" %%F in ('dir /s /b "%EX%\rtlsdr.dll" 2^>nul ^| findstr /i "x64"') do set "BLOGDLL=%%F"
if not defined BLOGDLL goto dlfail

copy /y "%BLOGDLL%" "%PKG%\rtlsdr.dll" >nul
if errorlevel 1 (
    echo Could not copy rtlsdr.dll into %PKG%
    goto fail
)
copy /y "%SITE%\libusb_package\libusb-1.0.dll" "%PKG%\libusb-1.0.dll" >nul
if errorlevel 1 (
    echo Could not copy libusb-1.0.dll into %PKG%
    goto fail
)
echo Driver DLLs installed in %PKG%

rem ---------- 4. Program files ----------
echo.
echo [4/5] Copying TinySDR to %INSTALL% ...
if not exist "%INSTALL%" mkdir "%INSTALL%"
copy /y "%~dp0tinysdr.py" "%INSTALL%\" >nul 2>&1
copy /y "%~dp0tinysdr.bat" "%INSTALL%\" >nul 2>&1
if not exist "%INSTALL%\tinysdr.py" (
    echo Could not copy files into %INSTALL%
    goto fail
)

rem ---------- 5. Desktop shortcut ----------
echo.
echo [5/5] Creating the desktop shortcut...
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\TinySDR.lnk'); $s.TargetPath='%INSTALL%\tinysdr.bat'; $s.WorkingDirectory='%INSTALL%'; $s.Save()"
if errorlevel 1 echo Could not create the shortcut, you can still run %INSTALL%\tinysdr.bat

rem ---------- check ----------
echo.
echo Checking that the driver DLL loads...
python -c "import ctypes,os; os.add_dll_directory(r'%PKG%'); ctypes.CDLL(r'%PKG%\rtlsdr.dll')" >nul 2>&1
if errorlevel 1 (
    echo WARNING: the driver DLL did not load. Install the latest Microsoft Visual C++ Redistributable x64 and run this installer again.
) else (
    echo Driver DLL loads OK.
)

echo.
echo ==================================================
echo  Done. Start TinySDR from the shortcut on your Desktop,
echo  or run %INSTALL%\tinysdr.bat
echo.
echo  ONE MANUAL STEP, only if you have not done it before:
echo  run Zadig, choose Options - List All Devices, pick
echo  "Bulk-In, Interface (Interface 0)" and install WinUSB.
echo ==================================================
echo.
choice /m "Open the Zadig download page now"
if errorlevel 2 goto end
start "" https://zadig.akeo.ie/
goto end

:dlfail
echo.
echo Could not get the driver DLL automatically.
echo Download Release.zip from https://github.com/rtlsdrblog/rtl-sdr-blog/releases
echo save it in the same folder as this installer, and run the installer again.
goto fail

:fail
echo.
echo Installation did not finish.
pause
exit /b 1

:end
pause
exit /b 0