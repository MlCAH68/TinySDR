# TinySDR

Thanks for downloading! TinySDR is a tiny, single-file software-defined radio receiver for RTL-SDR dongles. It runs in a clean terminal window and plays smooth audio through your speakers.

## Features
- **Modes:** WFM (broadcast FM), NFM (ham / public service), AM, USB, LSB
- **Tuning:** Arrow keys with adjustable step size, or type a frequency directly
- **HF Support:** Works natively with the RTL-SDR Blog V4 or via direct sampling on a V3 / generic dongle
- **Squelch & Signal Meter:** Adjustable squelch with a real-time signal strength meter bar and automatic audio boost so voices aren't quiet

---

## What You Need
- A Windows PC
- An RTL-SDR dongle (RTL-SDR Blog V3 or V4 recommended)
- Python 3 from python.org (*Tick "Add python.exe to PATH" during setup*)
- An antenna (*for HF you'll want a proper HF antenna, or you'll mostly hear noise*)

---

## Installation

### One-Click Installer
1. Keep these files together in one folder:
   - `tinysdr.py`
   - `tinysdr.bat`
   - `install.bat`
2. Double-click `install.bat`. It installs the required Python packages, puts the driver DLLs in the right place, copies TinySDR to `C:\TinySDR`, and creates a shortcut on your Desktop.
3. **One-time driver step (Zadig):** Plug in your dongle, run Zadig, choose **Options > List All Devices**, select **Bulk-In, Interface (Interface 0)**, and install the **WinUSB** driver. *(Skip this if the dongle already works in other SDR software).*

> *Note:* If the installer can't download the driver automatically, download `Release.zip` from the RTL-SDR Blog releases page, save it next to `install.bat`, and run the installer again.

---

## How to Run

Double-click the **TinySDR** shortcut on your Desktop (starts on 98.7 MHz WFM), or open Command Prompt and run:

```cmd
tinysdr.bat 98.7 wfm
tinysdr.bat 146.52 nfm
tinysdr.bat 7.2 lsb
tinysdr.bat 7.2 usb direct
