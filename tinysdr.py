#!/usr/bin/env python3
"""tinysdr.py - minimal single-file RTL-SDR receiver with working squelch, signal bar, and smooth audio.

Modes: WFM NFM AM USB LSB.
HF: RTL-SDR Blog V4 tunes HF natively. V3 / generic dongles: press 'd' (direct sampling).

  python tinysdr.py [freq_MHz] [mode]            e.g. python tinysdr.py 7.2 lsb

Keys:  <- ->  tune by step      [ ]  smaller / bigger step     f  type a frequency (MHz, or 7200k)
       m  mode                  b    band hop                  d  direct sampling (V3 HF)
       ^ v  volume              , .  squelch down / up (dB)     q  quit
"""
import sys, os, queue, threading, time

# Windows: make sure the DLLs next to the rtlsdr package are found first
import importlib.util, ctypes
_spec = importlib.util.find_spec("rtlsdr")
if _spec and _spec.submodule_search_locations:
    _d = list(_spec.submodule_search_locations)[0]
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(_d)
    os.environ["PATH"] = _d + os.pathsep + os.environ["PATH"]

# The RTL-SDR Blog driver lacks a few optional functions pyrtlsdr asks for
_orig_getattr = ctypes.CDLL.__getattr__
def _getattr(self, name):
    try:
        return _orig_getattr(self, name)
    except AttributeError:
        if name.startswith("__"):
            raise
        return lambda *a, **k: 0
ctypes.CDLL.__getattr__ = _getattr

import numpy as np
from scipy.signal import firwin, lfilter
from rtlsdr import RtlSdr
import sounddevice as sd

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

# Enable ANSI escape sequences on Windows 10/11
if os.name == 'nt':
    os.system('')

FS, D1, D2 = 960_000, 4, 5            # RF rate -> 240k IF -> 48k audio
IF, AF = FS // D1, FS // D1 // D2
N = 96_000                            # samples per block (0.1 s)
MODES = ["wfm", "nfm", "am", "usb", "lsb"]
STEPS = [10, 100, 500, 1_000, 5_000, 12_500, 25_000, 100_000, 1_000_000]
DEF_STEP = {"wfm": 100_000, "nfm": 12_500, "am": 5_000, "usb": 1_000, "lsb": 1_000}
DEF_SQL = {"wfm": 0, "nfm": 6, "am": 0, "usb": 0, "lsb": 0}   # squelch, dB over noise (0 = off)

CHAN = {"wfm": (405, 619), "nfm": (505, 519), "am": (507, 517), "usb": (513, 517), "lsb": (508, 512)}
BW = {"nfm": 12.5e3, "am": 10e3}
AUD = {"wfm": 15e3, "nfm": 4e3, "am": 4e3, "usb": 3e3, "lsb": 3e3}
BANDS = [(3.85e6, "lsb"), (7.2e6, "lsb"), (10.0e6, "am"), (14.2e6, "usb"),
         (21.3e6, "usb"), (28.4e6, "usb"), (98.7e6, "wfm"), (146.52e6, "nfm")]
WIN = np.hanning(1024)


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


class Filt:
    """Stateful FIR so block edges don't click."""
    def __init__(self, taps, dtype):
        self.b, self.z = taps, np.zeros(len(taps) - 1, dtype)
    def __call__(self, x):
        y, self.z = lfilter(self.b, 1.0, x, zi=self.z)
        return y


def ssb_taps(mode):
    n = 801
    shift = 1500 if mode == "usb" else -1500
    t = (np.arange(n) - (n - 1) / 2) / IF
    return firwin(n, 1200, fs=IF) * np.exp(2j * np.pi * shift * t)


def make_state(mode):
    st = dict(f1=Filt(firwin(65, 100e3, fs=FS), complex),
              fa=Filt(firwin(65, AUD[mode], fs=IF), float), last=0j, lvl=1e-3, level=0.0, open=True, g=0.0)
    if mode in BW:
        st["f2"] = Filt(firwin(257, BW[mode] / 2, fs=IF), complex)
    elif mode in ("usb", "lsb"):
        st["f2"] = Filt(ssb_taps(mode), complex)
    return st


def spectrum(iq):
    seg = iq[:8192].reshape(8, 1024) * WIN
    return np.fft.fftshift((np.abs(np.fft.fft(seg, axis=1)) ** 2).mean(0))


def sig_level(psd, mode):
    lo, hi = CHAN[mode]
    ch = psd[lo:hi]
    sig = ch.mean() if mode in ("usb", "lsb") else np.percentile(ch, 75)
    return 10 * np.log10(sig / np.median(psd) + 1e-12)


def agc(a, st, update, reset=False):
    if update:
        rms = np.sqrt(np.mean(a * a)) + 1e-9
        st["lvl"] = rms if reset else max(rms, st["lvl"] * 0.8)
    return a * min(0.5 / st["lvl"], 60.0)


def demod(iq, mode, st, sql, psd):
    x = st["f1"](iq)[::D1]
    if "f2" in st:
        x = st["f2"](x)
    was_open = st["open"]
    st["level"] = sig_level(psd, mode)
    st["open"] = op = sql <= 0 or st["level"] > (sql - 2 if was_open else sql)   # 2 dB hysteresis
    reopen = op and not was_open
    if mode == "am":
        a = np.abs(x)
        a = agc(a / (a.mean() + 1e-9) - 1.0, st, op, reopen)
    elif mode in ("usb", "lsb"):
        a = agc(x.real, st, op, reopen)
    else:
        d = np.concatenate(([st["last"]], x))
        st["last"] = x[-1]
        a = np.angle(d[1:] * np.conj(d[:-1]))
        a = a * 0.5 if mode == "wfm" else agc(a, st, op, reopen)
    out = st["fa"](a)[::D2].astype(np.float32)
    g = 1.0 if op else 0.0
    if st["g"] != g:
        out *= np.linspace(st["g"], g, len(out), endpoint=False, dtype=np.float32)
    elif g == 0.0:
        out *= 0
    st["g"] = g
    return out


def fmt_step(v):
    return f"{v/1e3:g} kHz" if v >= 1000 else f"{v} Hz"


def print_header(s):
    clear_screen()
    print("=== TinySDR Receiver ===")
    sq = "off" if s['sql'] <= 0 else f"{s['sql']}dB"
    print(f"Freq: {s['freq']/1e6:.5f} MHz | Mode: {s['mode'].upper()} | Step: {fmt_step(s['step'])} | Vol: {s['vol']:.1f} | Sql: {sq}{' [DIRECT]' if s['direct'] else ''}")
    print("Controls: <-/-> Tune | [/] Step | m Mode | d Direct | ^/v Vol | ,/. Sql | f Freq | q Quit")
    print("-" * 65 + "\n")


def draw(s):
    sq = "off" if s["sql"] <= 0 else f"{s['sql']}dB"
    bw = 20
    n = int(max(0.0, min(40.0, s["level"])) / 40 * bw)
    bar = ["#" if i < n else "-" for i in range(bw)]
    if s["sql"] > 0:
        bar[min(bw - 1, int(s["sql"] / 40 * bw))] = "|"
    status = (f"\rFreq: {s['freq']/1e6:11.5f} MHz | {s['mode'].upper()} | Vol: {s['vol']:.1f} | Sql: {sq} | "
              f"Sig [" + "".join(bar) + f"] {s['level']:+.0f}dB [{'OPEN' if s['open'] else 'quiet'}]   ")
    sys.stdout.write(status)
    sys.stdout.flush()


def main(freq, mode, direct):
    sdr = RtlSdr()
    sdr.sample_rate, sdr.center_freq, sdr.gain = FS, freq, "auto"
    s = dict(freq=freq, mode=mode, vol=1.0, run=True, st=make_state(mode),
             step=DEF_STEP[mode], direct=False, err="", sql=DEF_SQL[mode], level=0.0, open=True)
    s["cfg"] = (mode, s["st"])
    lock, iq_q, q = threading.Lock(), queue.Queue(maxsize=8), queue.Queue(maxsize=8)

    def set_freq(f):
        s["freq"] = max(1e3, f)
        with lock:
            sdr.center_freq = s["freq"]

    def set_mode(m):
        s["cfg"] = (m, make_state(m))
        s["mode"], s["step"], s["sql"] = m, DEF_STEP[m], DEF_SQL[m]
        print_header(s)

    def set_direct(on):
        with lock:
            try:
                sdr.set_direct_sampling(2 if on else 0)
                s["direct"] = on
            except Exception as e:
                s["direct"], s["err"] = False, str(e)[:40]
            sdr.center_freq = s["freq"]
        print_header(s)

    def rx():
        try:
            while s["run"]:
                with lock:
                    iq = sdr.read_samples(N)
                try: iq_q.put_nowait(iq)
                except queue.Full: pass
        except Exception as e:
            s["err"] = str(e)[:40]

    def proc():
        while s["run"]:
            try: iq = iq_q.get(timeout=0.5)
            except queue.Empty: continue
            try:
                mode, st = s["cfg"]
                audio = demod(iq, mode, st, s["sql"], spectrum(iq))
                s["level"], s["open"] = st["level"], st["open"]
                q.put(audio, timeout=0.5)
            except queue.Full: pass
            except Exception as e:
                s["err"] = str(e)[:40]

    primed = [False]
    def cb(out, frames, t, status):
        if not primed[0]:
            if q.qsize() < 2:
                out[:] = 0
                return
            primed[0] = True
        try: out[:, 0] = np.tanh(q.get_nowait() * s["vol"])
        except queue.Empty:
            out[:] = 0
            primed[0] = False

    if direct:
        set_direct(True)

    threading.Thread(target=rx, daemon=True).start()
    threading.Thread(target=proc, daemon=True).start()
    print_header(s)

    with sd.OutputStream(samplerate=AF, channels=1, blocksize=N // (D1 * D2),
                         dtype="float32", latency="high", callback=cb):
        while s["run"]:
            draw(s)
            
            if HAS_MSVCRT and msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch == b'q':
                    break
                elif ch == b'm':
                    set_mode(MODES[(MODES.index(s["mode"]) + 1) % len(MODES)])
                elif ch == b'd':
                    set_direct(not s["direct"])
                elif ch == b']':
                    s["step"] = next((v for v in STEPS if v > s["step"]), STEPS[-1])
                    print_header(s)
                elif ch == b'[':
                    s["step"] = next((v for v in reversed(STEPS) if v < s["step"]), STEPS[0])
                    print_header(s)
                elif ch == b',':
                    s["sql"] = max(0, s["sql"] - 1)
                    print_header(s)
                elif ch == b'.':
                    s["sql"] = min(40, s["sql"] + 1)
                    print_header(s)
                elif ch == b'f':
                    sys.stdout.write("\n\nType frequency in MHz (e.g. 98.7 or 7200k): ")
                    sys.stdout.flush()
                    try:
                        t = input().strip().lower().replace("hz", "")
                        if t:
                            set_freq(float(t.rstrip("km")) * (1e3 if t.endswith("k") else 1e6))
                    except ValueError:
                        pass
                    print_header(s)
                elif ch == b'b':
                    i = next((i for i, (f_band, m_band) in enumerate(BANDS) if f_band > s["freq"] + 1), 0)
                    set_mode(BANDS[i][1])
                    set_freq(BANDS[i][0])
                elif ch == b'\xe0':  # Special keys (arrows)
                    k2 = msvcrt.getch()
                    if k2 == b'M':    # Right arrow
                        set_freq(s["freq"] + s["step"])
                    elif k2 == b'K':  # Left arrow
                        set_freq(s["freq"] - s["step"])
                    elif k2 == b'H':  # Up arrow
                        s["vol"] = min(4.0, s["vol"] + 0.1)
                        print_header(s)
                    elif k2 == b'P':  # Down arrow
                        s["vol"] = max(0.0, s["vol"] - 0.1)
                        print_header(s)
            else:
                time.sleep(0.05)

    s["run"] = False
    sdr.close()
    print("\nExited TinySDR.")


if __name__ == "__main__":
    f = float(sys.argv[1]) * 1e6 if len(sys.argv) > 1 else 98.7e6
    m = sys.argv[2].lower() if len(sys.argv) > 2 else "wfm"
    if m not in MODES:
        sys.exit("mode must be one of: " + " ".join(MODES))
    main(f, m, "direct" in sys.argv[3:])