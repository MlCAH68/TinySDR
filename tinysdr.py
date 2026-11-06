#!/usr/bin/env python3
"""tinysdr.py - minimal single-file RTL-SDR receiver with a terminal UI (TUI).

Windows only (it uses the Windows console). Run it in Windows Terminal.
Modes: WFM NFM AM USB LSB, adjustable bandwidth, squelch, signal meter, optional spectrum.
HF: RTL-SDR Blog V4 tunes HF natively. V3 / generic dongles: press 'd' (direct sampling).

  pip install pyrtlsdr==0.5.1 numpy scipy sounddevice libusb-package
  python tinysdr.py [freq_MHz] [mode] [direct]   e.g. python tinysdr.py 7.2 lsb

Keys:  <- ->  tune by step       [ ]  smaller / bigger step     - +  narrower / wider bandwidth
       f  type a frequency       m    mode                      b    band hop
       ^ v  volume               , .  squelch down / up         d    HF direct sampling
       s  spectrum on / off      q    quit
"""
import sys, os, time, shutil, queue, threading, collections
import importlib.util, ctypes

try:
    import msvcrt
except ImportError:
    sys.exit("TinySDR needs Windows: it reads keys with msvcrt and draws in the Windows console.")

# ---------------------------------------------------------------------------
# Windows driver setup
# ---------------------------------------------------------------------------
# Make sure the DLLs that sit next to the rtlsdr package are found first.
_spec = importlib.util.find_spec("rtlsdr")
if _spec and _spec.submodule_search_locations:
    _d = list(_spec.submodule_search_locations)[0]
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(_d)
    os.environ["PATH"] = _d + os.pathsep + os.environ["PATH"]

# pyrtlsdr 0.5.1 binds some driver functions the RTL-SDR Blog DLL doesn't have (for example
# rtlsdr_set_dithering). Give those missing names a stub that returns 0 ("ok"). The two tuner
# bandwidth functions are left alone: pyrtlsdr checks for them itself with try/except.
# FAKED records which names were missing, and the UI shows them.
_NEVER_FAKE = {"rtlsdr_set_and_get_tuner_bandwidth", "rtlsdr_set_tuner_bandwidth"}
FAKED = []
_orig_getattr = ctypes.CDLL.__getattr__
def _getattr(self, name):
    try:
        return _orig_getattr(self, name)
    except AttributeError:
        if name.startswith("rtlsdr_") and name not in _NEVER_FAKE:
            FAKED.append(name[len("rtlsdr_"):])
            return lambda *a, **k: 0
        raise
ctypes.CDLL.__getattr__ = _getattr

import numpy as np
from scipy.signal import firwin, lfilter
from rtlsdr import RtlSdr
import sounddevice as sd

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
FS, D1, D2 = 960_000, 4, 5            # RF rate -> 240 kHz IF -> 48 kHz audio
IF, AF = FS // D1, FS // D1 // D2
N = 96_000                            # samples per block (0.1 s)
BIN = FS / 1024                       # width of one bin of the signal-meter FFT
TAU = 75e-6                           # WFM de-emphasis: 75 us in the Americas, 50e-6 in most other places

MODES = ["wfm", "nfm", "am", "usb", "lsb"]
STEPS = [10, 100, 500, 1_000, 5_000, 12_500, 25_000, 100_000, 1_000_000]
DEF_STEP = {"wfm": 100_000, "nfm": 12_500, "am": 5_000, "usb": 1_000, "lsb": 1_000}
DEF_SQL = {"wfm": 0, "nfm": 6, "am": 0, "usb": 0, "lsb": 0}        # dB over noise, 0 = off
BW_OPTS = {"wfm": [100e3, 150e3, 200e3],                           # channel / passband width, Hz
           "nfm": [6e3, 8e3, 12.5e3, 15e3, 20e3, 25e3],
           "am": [4e3, 6e3, 8e3, 10e3, 15e3],
           "usb": [1.8e3, 2.1e3, 2.4e3, 2.7e3, 3.0e3, 3.6e3],
           "lsb": [1.8e3, 2.1e3, 2.4e3, 2.7e3, 3.0e3, 3.6e3]}
DEF_BW = {"wfm": 200e3, "nfm": 12.5e3, "am": 10e3, "usb": 2.4e3, "lsb": 2.4e3}
SSB_LOW = 300                                                      # SSB passband starts 300 Hz off the carrier
BANDS = [(3.85e6, "lsb"), (7.2e6, "lsb"), (10.0e6, "am"), (14.2e6, "usb"),
         (21.3e6, "usb"), (28.4e6, "usb"), (98.7e6, "wfm"), (146.52e6, "nfm")]

_a = np.exp(-1.0 / (IF * TAU))
DEEMPH_B, DEEMPH_A = [1 - _a], [1.0, -_a]
WIN = np.hanning(1024)


# ---------------------------------------------------------------------------
# DSP
# ---------------------------------------------------------------------------
class Filt:
    """Stateful FIR filter, so block edges don't click."""
    def __init__(self, taps, dtype):
        self.b, self.z = taps, np.zeros(len(taps) - 1, dtype)
    def __call__(self, x):
        y, self.z = lfilter(self.b, 1.0, x, zi=self.z)
        return y


class Decim:
    """Low-pass FIR + keep every M-th sample, computed polyphase so only kept samples are calculated."""
    def __init__(self, taps, M, dtype=complex):
        L = -(-len(taps) // M) * M
        h = np.zeros(L)
        h[:len(taps)] = taps
        self.M = M
        self.branches = [Filt(h[p::M], dtype) for p in range(M)]
        self.carry = np.zeros(M - 1, dtype)
    def __call__(self, x):
        M, n = self.M, len(x) // self.M
        xx = np.concatenate((self.carry, x))
        self.carry = x[len(x) - (M - 1):].copy()
        y = 0
        for p, f in enumerate(self.branches):
            y = y + f(xx[M - 1 - p::M][:n])
        return y


def ssb_taps(mode, bw, n=161, fs=AF):
    """Complex band-pass (SSB_LOW .. SSB_LOW+bw) on the + side (USB) or - side (LSB)."""
    half = bw / 2
    shift = SSB_LOW + half if mode == "usb" else -(SSB_LOW + half)
    t = (np.arange(n) - (n - 1) / 2) / fs
    return firwin(n, half, fs=fs) * np.exp(2j * np.pi * shift * t)


def audio_cut(mode, bw):
    return {"wfm": 15e3, "nfm": min(bw * 0.32, 6e3), "am": min(bw / 2, 6e3)}[mode]


def make_state(mode, bw):
    st = dict(f1=Decim(firwin(65, 100e3, fs=FS), D1), bw=bw, last=0j, lvl=1e-3,
              level=0.0, open=True, g=0.0)
    if mode in ("usb", "lsb"):                       # drop to 48 kHz first, then the sideband filter
        st["f2"] = Filt(firwin(97, 10e3, fs=IF), complex)
        st["f3"] = Filt(ssb_taps(mode, bw), complex)
        return st
    if mode == "wfm":
        if bw < 200e3:
            st["f2"] = Filt(firwin(65, bw / 2, fs=IF), complex)
        st["de"] = np.zeros(1)
    else:
        st["f2"] = Filt(firwin(257, bw / 2, fs=IF), complex)
    st["fa"] = Filt(firwin(65, audio_cut(mode, bw), fs=IF), float)
    return st


def spectrum(iq):
    """Averaged power spectrum (1024 bins, centre-shifted): feeds the signal meter, squelch and spectrum."""
    seg = iq[:8192].reshape(8, 1024) * WIN
    return np.fft.fftshift((np.abs(np.fft.fft(seg, axis=1)) ** 2).mean(0))


def chan_bins(mode, bw):
    """Range of spectrum bins (centre = 512) that hold the channel."""
    if mode in ("usb", "lsb"):
        a = 1
        b = a + max(3, int(np.ceil(bw / BIN)) + 1)
        return (512 + a, 512 + b) if mode == "usb" else (512 - b + 1, 512 - a + 1)
    h = max(1, int(round(bw / 2 / BIN)))
    return 512 - h, 512 + h


def sig_level(psd, mode, bw):
    """Channel power over the noise floor (median of the whole span), in dB."""
    lo, hi = chan_bins(mode, bw)
    ch = psd[lo:hi]
    sig = ch.mean() if mode in ("usb", "lsb") else np.percentile(ch, 75)   # ignores the DC spike
    return 10 * np.log10(sig / np.median(psd) + 1e-12)


def agc(a, st, update, reset=False):
    """Boost to a steady level: fast attack, quick decay; frozen while squelched.
    On the block where the squelch opens, the level is re-measured from scratch."""
    if update:
        rms = np.sqrt(np.mean(a * a)) + 1e-9
        st["lvl"] = rms if reset else max(rms, st["lvl"] * 0.8)
    return a * min(0.5 / st["lvl"], 60.0)


def demod(iq, mode, st, sql, psd):
    x = st["f1"](iq)                                 # 960 kHz -> 240 kHz
    ssb = mode in ("usb", "lsb")
    if ssb:
        x = st["f3"](st["f2"](x)[::D2])              # 48 kHz from here on
    elif "f2" in st:
        x = st["f2"](x)
    was_open = st["open"]
    st["level"] = sig_level(psd, mode, st["bw"])
    st["open"] = op = sql <= 0 or st["level"] > (sql - 2 if was_open else sql)   # 2 dB hysteresis
    reopen = op and not was_open
    if ssb:
        a = agc(x.real, st, op, reopen)              # one-sided spectrum -> real part is the audio
    elif mode == "am":
        a = np.abs(x)
        a = agc(a / (a.mean() + 1e-9) - 1.0, st, op, reopen)
    else:
        d = np.concatenate(([st["last"]], x))
        st["last"] = x[-1]
        a = np.angle(d[1:] * np.conj(d[:-1]))
        if mode == "wfm":
            a, st["de"] = lfilter(DEEMPH_B, DEEMPH_A, a * 0.5, zi=st["de"])
        else:
            a = agc(a, st, op, reopen)
    out = (a if ssb else st["fa"](a)[::D2]).astype(np.float32)
    g = 1.0 if op else 0.0
    if st["g"] != g:                                 # fade over the block so squelch doesn't click
        out *= np.linspace(st["g"], g, len(out), endpoint=False, dtype=np.float32)
    elif g == 0.0:
        out *= 0
    st["g"] = g
    return out


# ---------------------------------------------------------------------------
# Terminal UI
# ---------------------------------------------------------------------------
ESC = "\x1b["
RESET = ESC + "0m"
BORDER, TITLE, DIM, TEXT = ESC + "36m", ESC + "92m", ESC + "90m", ESC + "97m"
BIG, GOOD, GOOD2, WARN, BAD, ACC = ESC + "1;96m", ESC + "32m", ESC + "92m", ESC + "33m", ESC + "31m", ESC + "95m"
BADGE = ESC + "1;7;95m"
SPARK = "▁▂▃▄▅▆▇█"
MIN_W, MIN_H = 80, 20

DIGITS = {
    "0": (" _ ", "| |", "|_|"), "1": ("   ", "  |", "  |"), "2": (" _ ", " _|", "|_ "),
    "3": (" _ ", " _|", " _|"), "4": ("   ", "|_|", "  |"), "5": (" _ ", "|_ ", " _|"),
    "6": (" _ ", "|_ ", "|_|"), "7": (" _ ", "  |", "  |"), "8": (" _ ", "|_|", "|_|"),
    "9": (" _ ", "|_|", " _|"), ".": (" ", " ", "."), " ": ("   ", "   ", "   "),
}


class Canvas:
    """A grid of styled characters, drawn to the terminal in one write."""
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.ch = [[" "] * w for _ in range(h)]
        self.st = [[""] * w for _ in range(h)]

    def put(self, x, y, text, style=""):
        if 0 <= y < self.h:
            for i, c in enumerate(text):
                if 0 <= x + i < self.w:
                    self.ch[y][x + i], self.st[y][x + i] = c, style

    def box(self, x, y, w, h, title=""):
        self.put(x, y, "╭" + "─" * (w - 2) + "╮", BORDER)
        for r in range(1, h - 1):
            self.put(x, y + r, "│" + " " * (w - 2) + "│", BORDER)
        self.put(x, y + h - 1, "╰" + "─" * (w - 2) + "╯", BORDER)
        if title:
            self.put(x + 2, y, " " + title + " ", TITLE)

    def render(self):
        out = []
        for y in range(self.h):
            parts, cur = [ESC + f"{y + 1};1H"], None
            for c, st in zip(self.ch[y], self.st[y]):
                if st != cur:
                    parts.append(RESET + st)
                    cur = st
                parts.append(c)
            out.append("".join(parts))
        return "".join(out) + RESET


def fmt_hz(v):
    return f"{v/1e3:g} kHz" if v >= 1000 else f"{v:g} Hz"


def hbar(cv, x, y, w, frac, color):
    n = int(round(max(0.0, min(1.0, frac)) * w))
    cv.put(x, y, "█" * n, color)
    cv.put(x + n, y, "░" * (w - n), DIM)


def sparkline(vals, w, hi):
    vals = list(vals)[-w:]
    s = "".join(SPARK[int(max(0.0, min(0.999, v / hi)) * 8)] for v in vals)
    return s.rjust(w)


def braille_chart(vals, cw, ch, lo, hi):
    """Line chart in a cw x ch cell grid, 2x4 dots per cell. Returns a numpy grid of dot bits."""
    dw, dh = cw * 2, ch * 4
    grid = np.zeros((ch, cw), np.uint16)
    bits = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
    vals = list(vals)[-dw:]
    off, prev = dw - len(vals), None
    for i, v in enumerate(vals):
        y = int(round((1 - (min(max(v, lo), hi) - lo) / (hi - lo)) * (dh - 1)))
        x = off + i
        y0 = y if prev is None else prev
        for yy in range(min(y, y0), max(y, y0) + 1):
            grid[yy // 4, x // 2] |= bits[yy % 4][x % 2]
        prev = y
    return grid


def build_frame(s, hist, W, H):
    cv = Canvas(W, H)
    if W < MIN_W or H < MIN_H:
        msg = f"Terminal too small: need {MIN_W}x{MIN_H}, have {W}x{H}. Enlarge the window."
        cv.put(0, 0, msg[:W], WARN)
        return cv.render()

    mode, level, sql, bw = s["mode"], s["level"], s["sql"], s["bw"]
    top_h, key_h = 8, 4
    mid_h = H - top_h - key_h
    left_w = max(52, W * 55 // 100)
    right_w = W - left_w

    # ---- radio panel -----------------------------------------------------------------------
    cv.box(0, 0, left_w, top_h, "radio")
    digits = ["", "", ""]
    for c in f"{s['freq'] / 1e6:9.5f}":
        g = DIGITS.get(c, DIGITS[" "])
        for i in range(3):
            digits[i] += g[i] + " "
    for i in range(3):
        cv.put(2, 1 + i, digits[i], BIG)
    dx = 2 + len(digits[0]) + 1
    cv.put(dx, 1, f" {mode.upper()} ", BADGE)
    cv.put(dx, 3, "MHz", TEXT)
    cv.put(2, 4, f"step {fmt_hz(s['step'])}   bandwidth {fmt_hz(bw)}", TEXT)
    cv.put(2, 5, "vol ", DIM)
    hbar(cv, 6, 5, 12, s["vol"] / 4.0, GOOD)
    cv.put(19, 5, f"{s['vol']:.1f}", TEXT)
    cv.put(25, 5, "sql ", DIM)
    cv.put(29, 5, "off" if sql <= 0 else f"{sql} dB", TEXT)
    if s["open"]:
        cv.put(left_w - 12, 5, "● OPEN", GOOD2)
    else:
        cv.put(left_w - 12, 5, "○ quiet", DIM)
    if s["err"]:
        cv.put(2, 6, ("ERR: " + s["err"])[:left_w - 4], BAD)
    else:
        notes = ("HF direct sampling ON   " if s["direct"] else "") + \
                ("driver lacks: " + ", ".join(sorted(set(FAKED))) if FAKED else "")
        cv.put(2, 6, notes[:left_w - 4], DIM)

    # ---- signal panel ----------------------------------------------------------------------
    cv.box(left_w, 0, right_w, top_h, "signal")
    iw = right_w - 4
    bar_w = max(8, iw - 6)
    frac = level / 40.0
    cv.put(left_w + 2, 1, "level", DIM)
    hbar(cv, left_w + 2, 2, bar_w, frac, GOOD if frac < 0.6 else (WARN if frac < 0.85 else BAD))
    if sql > 0:
        cv.put(left_w + 2 + min(bar_w - 1, int(min(sql, 40) / 40 * bar_w)), 2, "┃", ESC + "1;97m")
    cv.put(left_w + 2 + bar_w + 1, 2, f"{int(max(0, min(100, frac * 100))):>3d}%", TEXT)
    cv.put(left_w + 2, 3, f"{level:+.0f} dB over noise", TEXT)
    cv.put(left_w + 2, 4, sparkline(list(hist)[-iw:], iw, 40.0), ESC + "36m")
    cv.put(left_w + 2, 5, "audio", DIM)
    hbar(cv, left_w + 8, 5, max(4, iw - 6), min(1.0, s["vu"] * 3), GOOD2)

    # ---- history chart (+ spectrum) --------------------------------------------------------
    show_spec = s["spec_on"] and s["psd"] is not None
    hist_w = W // 2 if show_spec else W
    cv.box(0, top_h, hist_w, mid_h, "history" if show_spec else "signal history  (60 s)")
    cw, chh = hist_w - 4 - 4, mid_h - 2
    vals = list(hist)[-cw * 2:]
    hi = 20.0 * np.ceil(max(20.0, max(vals) if vals else 20.0) / 20.0)
    grid = braille_chart(vals, cw, chh, 0.0, hi)
    ty = None
    if sql > 0:
        ty = int((1 - min(sql, hi) / hi) * (chh * 4 - 1)) // 4
    for r in range(chh):
        label = f"{hi:>3.0f}" if r == 0 else (f"{hi / 2:>3.0f}" if r == chh // 2 else ("  0" if r == chh - 1 else "   "))
        cv.put(2, top_h + 1 + r, label + "┤", DIM)
        row = "".join(chr(0x2800 + int(v)) for v in grid[r])
        cv.put(7, top_h + 1 + r, row, GOOD2)
        if r == ty:
            for c in range(cw):
                if grid[r][c] == 0:
                    cv.put(7 + c, top_h + 1 + r, "┈", WARN)

    if show_spec:
        sx, sw = hist_w, W - hist_w
        cv.box(sx, top_h, sw, mid_h, "spectrum")
        cols, rows = sw - 4, mid_h - 4
        p = 10 * np.log10(s["psd"] + 1e-12)
        edges = np.linspace(0, 1024, cols + 1).astype(int)
        colv = np.maximum.reduceat(p, edges[:-1])
        floor = np.median(p)
        top = max(p.max(), floor + 15.0)
        h8 = (np.clip((colv - floor + 2) / (top - floor + 2), 0, 1) * rows * 8).astype(int)
        for r in range(rows):
            line = []
            for c in range(cols):
                v = int(h8[c]) - (rows - 1 - r) * 8
                line.append("█" if v >= 8 else (SPARK[v - 1] if v > 0 else " "))
            color = BAD if r < rows * 0.2 else (WARN if r < rows * 0.45 else GOOD2)
            cv.put(sx + 2, top_h + 1 + r, "".join(line), color)
        axis_y = top_h + 1 + rows
        cv.put(sx + 2, axis_y, "─" * cols, DIM)
        if mode == "usb":
            lo_hz, hi_hz = SSB_LOW, SSB_LOW + bw
        elif mode == "lsb":
            lo_hz, hi_hz = -(SSB_LOW + bw), -SSB_LOW
        else:
            lo_hz, hi_hz = -bw / 2, bw / 2
        c0 = max(0, min(cols - 1, int((lo_hz + FS / 2) / FS * cols)))
        c1 = max(c0, min(cols - 1, int((hi_hz + FS / 2) / FS * cols)))
        cv.put(sx + 2 + c0, axis_y, "━" * (c1 - c0 + 1), WARN)
        cv.put(sx + 2 + cols // 2, axis_y, "┼" if c0 > cols // 2 or c1 < cols // 2 else "╋", TEXT)
        left, mid, right = f"{(s['freq'] - FS / 2) / 1e6:.2f}", f"{s['freq'] / 1e6:.3f}", f"{(s['freq'] + FS / 2) / 1e6:.2f}"
        cv.put(sx + 2, axis_y + 1, left, DIM)
        cv.put(sx + 2 + cols // 2 - len(mid) // 2, axis_y + 1, mid, TEXT)
        cv.put(sx + 2 + cols - len(right), axis_y + 1, right, DIM)

    # ---- keys ------------------------------------------------------------------------------
    ky = H - key_h
    cv.box(0, ky, W, key_h, "keys")
    cv.put(2, ky + 1, "←/→ tune    [ ] step    - + bandwidth    f frequency    m mode    b band hop", TEXT)
    cv.put(2, ky + 2, "↑/↓ volume    , . squelch    d HF direct    s spectrum    q quit", TEXT)
    return cv.render()


def getkey(timeout=0.05):
    """Wait up to `timeout` s for a key: 'UP' 'DOWN' 'LEFT' 'RIGHT', a character, '' for other special keys, or None."""
    end = time.time() + timeout
    while True:
        if msvcrt.kbhit():
            c = msvcrt.getwch()
            if c in ("\x00", "\xe0"):                       # arrow / function key prefix (numpad sends \x00)
                return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}.get(msvcrt.getwch(), "")
            return c.lower() if c.isalpha() else c           # Caps Lock shouldn't matter
        if time.time() >= end:
            return None
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(freq, mode, direct):
    mcfg = {m: dict(step=DEF_STEP[m], sql=DEF_SQL[m], bw=DEF_BW[m]) for m in MODES}
    s = dict(freq=freq, mode=mode, vol=1.0, run=True, err="", open=True, level=0.0, vu=0.0,
             direct=False, want_direct=bool(direct), spec_on=False, psd=None, tick=0,
             step=mcfg[mode]["step"], sql=mcfg[mode]["sql"], bw=mcfg[mode]["bw"])
    s["cfg"] = (mode, make_state(mode, s["bw"]))     # (mode, state) is swapped as one unit
    hist = collections.deque(maxlen=1200)             # signal level, 10 per second
    iq_q, q = queue.Queue(maxsize=8), queue.Queue(maxsize=8)

    def set_freq(f):
        s["freq"] = max(1e3, f)                       # the reader thread applies it between reads

    def set_mode(m):
        mcfg[s["mode"]].update(step=s["step"], sql=s["sql"], bw=s["bw"])   # remember per-mode settings
        c = mcfg[m]
        s["mode"], s["step"], s["sql"], s["bw"] = m, c["step"], c["sql"], c["bw"]
        s["cfg"] = (m, make_state(m, s["bw"]))

    def set_bw(delta):
        opts = BW_OPTS[s["mode"]]
        i = min(range(len(opts)), key=lambda k: abs(opts[k] - s["bw"]))
        s["bw"] = opts[max(0, min(len(opts) - 1, i + delta))]
        s["cfg"] = (s["mode"], make_state(s["mode"], s["bw"]))

    def rx():
        """The only thread that touches the dongle: applies tuning requests, reads blocks, reconnects."""
        sdr, applied, stage = None, dict(freq=None, direct=False), ""
        while s["run"]:
            try:
                if sdr is None:
                    stage = "open"
                    sdr = RtlSdr()
                    sdr.sample_rate = FS
                    sdr.gain = "auto"
                    applied.update(freq=None, direct=False)
                if applied["direct"] != s["want_direct"]:
                    stage = "direct"
                    sdr.set_direct_sampling(2 if s["want_direct"] else 0)
                    applied["direct"] = s["direct"] = s["want_direct"]
                    applied["freq"] = None
                f = s["freq"]
                if applied["freq"] != f:
                    stage = "freq"
                    sdr.center_freq = f
                    applied["freq"] = f
                stage = "read"
                iq = sdr.read_samples(N)
                if s["err"]:
                    s["err"] = ""
                try: iq_q.put_nowait(iq)
                except queue.Full: pass               # processing fell behind: drop a block
            except Exception as e:
                s["err"] = f"{type(e).__name__}: {e}"[:70]
                if stage == "direct":
                    s["want_direct"] = applied["direct"]           # undo the request that failed
                elif stage == "freq" and applied["freq"] is not None:
                    s["freq"] = applied["freq"]                    # show the frequency we are really on
                if sdr is not None and not sdr.device_opened:      # pyrtlsdr closes the dongle on tune/read errors
                    sdr = None
                if sdr is None or stage == "read" or (stage == "freq" and applied["freq"] is None):
                    time.sleep(0.3)                                # wait before reopening / retrying
                # a rejected direct-sampling request was already undone and the dongle is fine: carry on at once
        if sdr is not None:
            sdr.close()

    def proc():
        """Demodulate blocks and hand the audio to the sound callback."""
        while s["run"]:
            try: iq = iq_q.get(timeout=0.5)
            except queue.Empty: continue
            try:
                m, st = s["cfg"]
                psd = spectrum(iq)
                audio = demod(iq, m, st, s["sql"], psd)
                s["level"], s["open"] = st["level"], st["open"]
                s["psd"] = psd if s["psd"] is None else 0.5 * s["psd"] + 0.5 * psd
                s["vu"] = float(np.sqrt(np.mean(audio * audio)))
                hist.append(st["level"])
                s["tick"] += 1
                q.put(audio, timeout=0.5)
            except queue.Full: pass
            except Exception as e:
                s["err"] = f"{type(e).__name__}: {e}"[:70]

    primed = [False]
    def cb(out, frames, t, status):
        if not primed[0]:                             # wait for a small cushion before playing
            if q.qsize() < 2:
                out[:] = 0
                return
            primed[0] = True
        try: out[:, 0] = np.tanh(q.get_nowait() * s["vol"])
        except queue.Empty:
            out[:] = 0
            primed[0] = False                         # underrun: rebuild the cushion

    rx_t = threading.Thread(target=rx, daemon=True)
    proc_t = threading.Thread(target=proc, daemon=True)
    rx_t.start()
    proc_t.start()
    os.system("")                                     # turns on ANSI escape codes in the Windows console
    sys.stdout.write(ESC + "?1049h" + ESC + "?25l" + ESC + "2J")     # alternate screen, hide cursor
    try:
        with sd.OutputStream(samplerate=AF, channels=1, blocksize=N // (D1 * D2),
                             dtype="float32", latency="high", callback=cb):
            last, last_t = None, 0.0
            while True:
                size = shutil.get_terminal_size((100, 30))
                sig = (s["tick"], s["freq"], s["mode"], s["step"], s["bw"], s["vol"], s["sql"],
                       s["direct"], s["spec_on"], s["err"], size)
                if sig != last or time.time() - last_t > 0.5:
                    last, last_t = sig, time.time()
                    sys.stdout.write(build_frame(s, hist, size.columns, size.lines))
                    sys.stdout.flush()
                k = getkey()
                if not k:
                    continue
                if k in ("q", "\x03"): break
                elif k == "RIGHT": set_freq(s["freq"] + s["step"])
                elif k == "LEFT": set_freq(s["freq"] - s["step"])
                elif k == "UP": s["vol"] = min(4.0, s["vol"] + 0.1)
                elif k == "DOWN": s["vol"] = max(0.0, s["vol"] - 0.1)
                elif k == ",": s["sql"] = max(0, s["sql"] - 1)
                elif k == ".": s["sql"] = min(40, s["sql"] + 1)
                elif k == "m": set_mode(MODES[(MODES.index(s["mode"]) + 1) % len(MODES)])
                elif k == "]": s["step"] = next((v for v in STEPS if v > s["step"]), STEPS[-1])
                elif k == "[": s["step"] = next((v for v in reversed(STEPS) if v < s["step"]), STEPS[0])
                elif k in ("-", "_"): set_bw(-1)
                elif k in ("+", "="): set_bw(+1)
                elif k == "d": s["want_direct"] = not s["want_direct"]
                elif k == "s": s["spec_on"] = not s["spec_on"]
                elif k == "b":
                    i = next((i for i, (f, m) in enumerate(BANDS) if f > s["freq"] + 1), 0)
                    set_mode(BANDS[i][1])
                    set_freq(BANDS[i][0])
                elif k == "f":
                    sys.stdout.write(ESC + f"{size.lines};1H" + ESC + "2K" + ESC + "?25h")
                    sys.stdout.flush()
                    try: t = input("Frequency (MHz, or 7200k for kHz): ").strip().lower().replace("hz", "")
                    except (EOFError, KeyboardInterrupt): t = ""
                    sys.stdout.write(ESC + "?25l")
                    try:
                        if t:
                            set_freq(float(t.rstrip("km")) * (1e3 if t.endswith("k") else 1e6))
                    except ValueError:
                        s["err"] = f"can't read '{t}' as a frequency"
                    last = None
    finally:
        s["run"] = False
        rx_t.join(timeout=1.0)                        # let the current read finish, then the reader closes the dongle
        sys.stdout.write(RESET + ESC + "?25h" + ESC + "?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        f = float(sys.argv[1]) * 1e6 if len(sys.argv) > 1 else 98.7e6
    except ValueError:
        sys.exit("usage: tinysdr.py [freq_MHz] [mode] [direct]")
    m = sys.argv[2].lower() if len(sys.argv) > 2 else "wfm"
    if m not in MODES:
        sys.exit("mode must be one of: " + " ".join(MODES))
    try:
        main(f, m, "direct" in sys.argv[3:])
    except Exception as e:
        sys.exit(f"TinySDR stopped: {type(e).__name__}: {e}")
