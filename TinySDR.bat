@echo off
rem Launches tinysdr.py from the folder this file is in.
rem Double-click to start on 98.7 WFM, or pass arguments:
rem   tinysdr.bat 7.2 lsb
rem   tinysdr.bat 7.2 usb direct
cd /d "%~dp0"
if "%~1"=="" (
    python tinysdr.py 98.7 wfm
) else (
    python tinysdr.py %*
)
if errorlevel 1 pause
 