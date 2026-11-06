TinySDR

Thanks for downloading! TinySDR is a tiny, single-file software-defined radio receiver for RTL-SDR dongles. It runs in a terminal window and plays smooth audio through your speakers.

Modes: WFM (broadcast FM), NFM (ham / public service), AM, USB, LSB
Tuning: arrow keys with adjustable step size, or type a frequency
HF: works with the RTL-SDR Blog V4 or with direct sampling on a V3 / generic dongle
Squelch with a signal meter, and automatic audio boost so voices aren't quiet

What you need
A Windows PC
An RTL-SDR dongle (RTL-SDR Blog V3 or V4 recommended)
Python 3 from python.org. Tick Add python.exe to PATH during setup.
An antenna (for HF you'll want a proper HF antenna, or you'll mostly hear noise)

Install
Keep these files together in one folder:
tinysdr.py
tinysdr.bat
install.bat

Double-click install.bat. It installs the Python packages, puts the driver DLLs in the right place, copies TinySDR to C:\TinySDR, and puts a TinySDR shortcut on your Desktop.
One-time driver step (Zadig): plug in the dongle, run Zadig, choose Options > List All Devices, pick Bulk-In, Interface (Interface 0), and install WinUSB. Skip this if the dongle already works in other SDR software.

If the installer can't download the driver, download Release.zip from the RTL-SDR Blog releases page, save it next to install.bat, and run the installer again.

Run

Double-click the TinySDR shortcut (starts on 98.7 MHz WFM), or open Command Prompt and use:

tinysdr.bat 98.7 wfm
tinysdr.bat 146.52 nfm
tinysdr.bat 7.2 lsb
tinysdr.bat 7.2 usb direct

Format is tinysdr.bat <frequency in MHz> <mode> [direct]. Modes: wfm, nfm, am, usb, lsb. Add direct to start with direct sampling (V3 HF).

Controls
Key    Action
Left / Right    Tune down / up by the current step
[ / ]    Smaller / bigger step (10 Hz up to 1 MHz)
f    Type a frequency: 7.2 or 146.52 (MHz), or 7200k (kHz), then Enter
m    Cycle mode: WFM, NFM, AM, USB, LSB
b    Jump to the next preset band (80m, 40m, WWV 10 MHz, 20m, 15m, 10m, 146.52 NFM, 98.7 WFM)
d    Toggle direct sampling (HF on V3 / generic dongles)
Up / Down    Volume (0 to 4.0)
, / .    Squelch down / up, in dB
q    Quit

Squelch and the signal meter

The status line shows something like sql 6dB  sig +17dB OPEN:

sig is how far the signal in the channel is above the noise on the rest of the band.
sql is the squelch threshold. Audio plays only while sig is above it.
The bar under the status line shows the same thing, with a | marking the squelch threshold.

Squelch defaults to 6 dB for NFM and off for every other mode. If static gets through, press . to raise it. If it cuts off weak signals, press , to lower it. 0 means off.

Tips
USB / LSB: tune to the dial frequency. The passband is 300 to 2700 Hz. Use the small steps (10 Hz, 100 Hz) to fine-tune a voice. By convention, use LSB below 10 MHz and USB above.
HF with a V4: just type the frequency. No direct sampling needed.
HF with a V3 or generic dongle: press d (or start with direct).
Window size: a bigger terminal window shows a longer signal meter.
Run it in Windows Terminal or Command Prompt. Some editor consoles don't handle the arrow keys properly.

Troubleshooting
Problem    Fix
Error loading librtlsdr    The driver DLLs aren't in the right place. Run install.bat again, or copy rtlsdr.dll and libusb-1.0.dll (64-bit) into the rtlsdr folder inside your Python site-packages.
No such device / usb_open error    The WinUSB driver isn't installed. Do the Zadig step above. Also close any other SDR program using the dongle.
Audio is quiet    Press Up to raise the volume (to 4.0). Make sure squelch isn't too high. The auto-boost needs a signal that is above the squelch.
Lots of static    Raise the squelch with .
Audio cuts out    Close other programs that use the dongle or heavy CPU. Multi-threaded architecture keeps audio smooth.
Garbled screen or keys do nothing    Use Windows Terminal or Command Prompt instead of an editor's built-in console.
Driver DLL won't load (WARNING at the end of the installer)    Install the latest Microsoft Visual C++ Redistributable x64, then run install.bat again.

Manual install (if you don't want to use install.bat)
pip install pyrtlsdr numpy scipy sounddevice libusb-package

Then copy rtlsdr.dll (from the x64 folder of the RTL-SDR Blog Release.zip) and libusb-1.0.dll into the rtlsdr folder inside your Python site-packages, and run python tinysdr.py 98.7 wfm.

Files
File    What it is
tinysdr.py    The receiver
tinysdr.bat    Launcher (double-click, or pass a frequency and mode)
install.bat    One-click installer
README.md    This file

Update log

v0.7

Replaced curses and windows-curses with native Windows msvcrt handling and ANSI control sequences for full compatibility with modern Python environments (Python 3.15+).
Restored multi-threaded audio queue buffering (rx and proc threads) to completely eliminate audio dropouts.
Synchronized real-time squelch and signal meter updates across the terminal header.

v0.6

Removed the spectrum analyzer (it used CPU and was linked to audio glitches).
Fixed audio cutting out at a steady rate: reading from the dongle and processing now run in separate threads, and audio keeps a small cushion before playing.
Stronger auto-boost for quiet signals. The gain is re-measured the moment the squelch opens. Maximum volume raised to 4.0.
Squelch now fades in and out instead of clicking.
Added a signal meter bar with a squelch marker.

v0.5

Added adjustable squelch (, and .) and a signal level readout.
Added automatic gain control for NFM, AM and SSB.
Default volume raised to 1.0.

v0.4

Replaced the waterfall with a lighter bar spectrum analyzer.
Added typed frequency entry (f), in MHz or with a k for kHz.

v0.3

Added adjustable tuning step ([ and ]).
Added USB and LSB modes.
Added HF support: native on V4, direct sampling (d) on V3 and generic dongles.
Added band hop (b).
Added a text waterfall display.

v0.2

Windows fixes: the program now finds the driver DLLs in the rtlsdr package folder, and works around the RTL-SDR Blog driver lacking a function that newer pyrtlsdr versions ask for.
Added tinysdr.bat launcher and install.bat installer.

v0.1

First version: WFM, NFM and AM receiver with arrow-key tuning and volume.

Credits
Built on pyrtlsdr, NumPy, SciPy, python-sounddevice, the RTL-SDR Blog driver, libusb and Zadig.
