# TinySDR

Thanks for downloading! TinySDR is a small, single-file software-defined radio receiver for RTL-SDR dongles. It runs in a terminal window as a full-screen text interface and plays audio through your speakers.

- **Modes:** WFM (broadcast FM), NFM (ham / public service), AM, USB, LSB
- **Tuning:** arrow keys with an adjustable step, or type a frequency
- **Bandwidth:** adjustable for every mode
- **HF:** works with the RTL-SDR Blog V4, or with direct sampling on a V3 / generic dongle
- **Squelch** with a live signal meter, and automatic audio boost so voices aren't quiet
- **Screen:** big frequency readout, signal gauge, signal history chart, and an optional spectrum view

## What you need

- A Windows PC
- An RTL-SDR dongle (RTL-SDR Blog V3 or V4 recommended)
- Python 3.9 or newer from [python.org](https://www.python.org/downloads/). Tick **Add python.exe to PATH** during setup. Any recent version works, including the newest.
- **Windows Terminal** (the default terminal on Windows 11) so the box-drawing and chart characters display properly
- An antenna (for HF you'll want a proper HF antenna, or you'll mostly hear noise)

## Install

1. Keep these files together in one folder:
   - `tinysdr.py`
   - `tinysdr.bat`
   - `install.bat`
2. Double-click **`install.bat`**. It installs the Python packages, puts the driver DLLs in the right place, copies TinySDR to `C:\TinySDR`, and puts a **TinySDR** shortcut on your Desktop.
3. **One-time driver step (Zadig):** plug in the dongle, run [Zadig](https://zadig.akeo.ie/), choose *Options > List All Devices*, pick **Bulk-In, Interface (Interface 0)**, and install **WinUSB**. Skip this if the dongle already works in other SDR software.

If the installer can't download the driver, download `Release.zip` from the [RTL-SDR Blog releases page](https://github.com/rtlsdrblog/rtl-sdr-blog/releases), save it next to `install.bat`, and run the installer again.

## Run

Double-click the **TinySDR** shortcut (starts on 98.7 MHz WFM), or open a terminal and use:

```
tinysdr.bat 146.52 nfm
tinysdr.bat 7.2 lsb
tinysdr.bat 7.2 usb direct
```

Format is `tinysdr.bat <frequency in MHz> <mode> [direct]`. Modes: `wfm`, `nfm`, `am`, `usb`, `lsb`. Add `direct` to start with direct sampling (V3 HF).

The window needs to be at least 80 columns by 20 rows. A bigger window gives bigger charts.

## The screen

- **radio:** the frequency, mode, step, bandwidth, volume and squelch. Errors show here in red.
- **signal:** a level gauge (the `┃` marks your squelch setting), a short history sparkline, and the audio level.
- **signal history:** a chart of the last 60 seconds of signal strength. The dashed line is the squelch threshold.
- **spectrum** (press `s`): the whole 960 kHz your dongle is hearing. The yellow `━` under the chart shows the part you are listening to (your bandwidth), and the centre mark is the tuned frequency.
- **keys:** a reminder of the controls.

## Controls

| Key | Action |
|-----|--------|
| Left / Right | Tune down / up by the current step |
| `[` / `]` | Smaller / bigger step (10 Hz up to 1 MHz) |
| `-` / `+` | Narrower / wider bandwidth |
| `f` | Type a frequency: `7.2` or `146.52` (MHz), or `7200k` (kHz), then Enter |
| `m` | Cycle mode: WFM, NFM, AM, USB, LSB |
| `b` | Jump to the next preset band (80m, 40m, WWV 10 MHz, 20m, 15m, 10m, 146.52 NFM, 98.7 WFM) |
| `d` | Toggle direct sampling (HF on V3 / generic dongles) |
| `s` | Show / hide the spectrum |
| Up / Down | Volume (0 to 4.0) |
| `,` / `.` | Squelch down / up, in dB |
| `q` | Quit |

Step, bandwidth and squelch are remembered for each mode while the program is running.

## Bandwidth

Press `-` or `+` to step through the choices for the current mode:

| Mode | Choices | Default |
|------|---------|---------|
| WFM | 100, 150, 200 kHz | 200 kHz |
| NFM | 6, 8, 12.5, 15, 20, 25 kHz | 12.5 kHz |
| AM | 4, 6, 8, 10, 15 kHz | 10 kHz |
| USB / LSB | 1.8, 2.1, 2.4, 2.7, 3.0, 3.6 kHz | 2.4 kHz |

Narrower cuts out more of the noise and the stations next door, wider sounds fuller. This is a software filter, so it works the same on every dongle. For SSB, the passband starts 300 Hz from the tuned frequency and is as wide as the setting.

## Squelch and the signal meter

The radio panel shows `sql 6 dB` and the signal panel shows how far the signal is above the noise, for example `+17 dB over noise`.

- Audio plays only while the signal is above the squelch setting.
- Squelch defaults to 6 dB for NFM and off for every other mode. Press `.` if static gets through, and `,` if it cuts off weak signals. `0` means off.
- When the squelch opens, the automatic volume boost re-measures the signal straight away, so voices come up loud.

## Tips

- **USB / LSB:** tune to the dial frequency. Use the small steps (10 Hz, 100 Hz) to fine-tune a voice. By convention, use LSB below 10 MHz and USB above.
- **HF with a V4:** just type the frequency. No direct sampling needed.
- **HF with a V3 or generic dongle:** press `d` (or start with `direct`).
- **WFM de-emphasis** is set for the Americas (75 microseconds). Outside the Americas, change `TAU = 75e-6` to `50e-6` near the top of `tinysdr.py`.
- **Unplugged the dongle?** TinySDR shows an error and reconnects by itself when you plug it back in.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Error loading librtlsdr` | The driver DLLs aren't in the right place. Run `install.bat` again, or copy `rtlsdr.dll` and `libusb-1.0.dll` (64-bit) into the `rtlsdr` folder inside your Python `site-packages`. |
| `ERR: ... Could not open SDR` | The dongle isn't found. Check it's plugged in, close any other SDR program using it, and do the Zadig step above. |
| `ERR: ... Could not set center_freq` | The dongle refused that frequency (for example, outside its range). TinySDR keeps the last good frequency. |
| `driver lacks: ...` in the radio panel | Information only: the RTL-SDR Blog driver doesn't include some optional functions and TinySDR works around it. |
| `Terminal too small` | Make the window at least 80 columns by 20 rows. |
| Odd boxes instead of charts | Use Windows Terminal. Old console windows can't show the chart characters. |
| Audio is quiet | Press Up to raise the volume (to 4.0). Make sure squelch isn't too high. |
| Lots of static | Raise the squelch with `.`, or narrow the bandwidth with `-`. |
| Audio cuts out | Close other programs that use the dongle or lots of CPU. If it keeps happening, note how often and whether squelch is on. |
| Driver DLL won't load (WARNING at the end of the installer) | Install the latest *Microsoft Visual C++ Redistributable x64*, then run `install.bat` again. |

## Manual install (if you don't want to use install.bat)

```
pip install -r requirements.txt
```

Then copy `rtlsdr.dll` (from the `x64` folder of the RTL-SDR Blog `Release.zip`) and `libusb-1.0.dll` into the `rtlsdr` folder inside your Python `site-packages`, and run `python tinysdr.py 98.7 wfm`.

`pyrtlsdr` is pinned to 0.5.1 on purpose: TinySDR works around a mismatch between that version and the Blog driver, and a newer release could change what it expects.

## Files

| File | What it is |
|------|------------|
| `tinysdr.py` | The receiver |
| `tinysdr.bat` | Launcher (double-click, or pass a frequency and mode) |
| `install.bat` | One-click installer |
| `requirements.txt` | The Python packages TinySDR needs |
| `README.md` | This file |

## Update log

**v0.7**
- New full-screen terminal interface: panels, big frequency readout, signal gauge, signal history chart, and an optional spectrum view (`s`) that also shows your bandwidth.
- Adjustable bandwidth for every mode (`-` and `+`), remembered per mode. Added a bandwidth readout.
- No longer needs `windows-curses`, which has no builds for new Python versions and made the installer fail. TinySDR now works on any Python 3.9 or newer.
- Errors are shown on screen. A rejected frequency or direct-sampling request no longer crashes the program, and unplugging the dongle shows an error and reconnects when it is plugged back in.
- Only one thread talks to the dongle, so tuning no longer waits behind a sample read.
- Clean shutdown: the dongle is closed properly, even with Ctrl+C.
- WFM now has de-emphasis (75 microseconds), so broadcast FM is less harsh and hissy.
- Lower CPU use: the first filter-and-decimate stage skips samples that would be thrown away, and the SSB filter runs at 48 kHz instead of 240 kHz.
- The driver workaround now only stubs missing `rtlsdr_` functions (not the tuner bandwidth ones that `pyrtlsdr` checks for itself), and the panel lists what the driver lacks.
- Keys: numpad arrows now work and Caps Lock no longer breaks letter keys.
- Installer pins `pyrtlsdr` 0.5.1. Added `requirements.txt`.

**v0.6**
- Removed the old spectrum analyzer (it used CPU and was linked to audio glitches).
- Fixed audio cutting out at a steady rate: reading from the dongle and processing now run in separate threads, and audio keeps a small cushion before playing.
- Stronger auto-boost for quiet signals. The gain is re-measured the moment the squelch opens. Maximum volume raised to 4.0.
- Squelch now fades in and out instead of clicking.
- Added a signal meter bar with a squelch marker.

**v0.5**
- Added adjustable squelch (`,` and `.`) and a signal level readout.
- Added automatic gain control for NFM, AM and SSB.
- Default volume raised to 1.0.

**v0.4**
- Replaced the waterfall with a lighter bar spectrum analyzer.
- Added typed frequency entry (`f`), in MHz or with a `k` for kHz.

**v0.3**
- Added adjustable tuning step (`[` and `]`).
- Added USB and LSB modes.
- Added HF support: native on V4, direct sampling (`d`) on V3 and generic dongles.
- Added band hop (`b`).
- Added a text waterfall display.

**v0.2**
- Windows fixes: the program now finds the driver DLLs in the `rtlsdr` package folder, and works around the RTL-SDR Blog driver lacking a function that newer `pyrtlsdr` versions ask for.
- Added `tinysdr.bat` launcher and `install.bat` installer.

**v0.1**
- First version: WFM, NFM and AM receiver with arrow-key tuning and volume.

## Credits

Built on [pyrtlsdr](https://github.com/pyrtlsdr/pyrtlsdr), [NumPy](https://numpy.org/), [SciPy](https://scipy.org/), [python-sounddevice](https://python-sounddevice.readthedocs.io/), the [RTL-SDR Blog driver](https://github.com/rtlsdrblog/rtl-sdr-blog), [libusb](https://libusb.info/) and [Zadig](https://zadig.akeo.ie/).
