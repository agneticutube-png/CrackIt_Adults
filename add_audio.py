#!/usr/bin/env python3
"""
Audio layer for riddle Shorts (stage 2 of pipeline).

ADULT: silent until the countdown, then a HEARTBEAT countdown -- one organic
lub-dub per second across the countdown window, nothing else (no drone bed,
no reveal chord). Every beat is identical. 100% synthesized -> never
Content-ID claimable.

Usage: python3 add_audio.py <input_video.mp4> [countdown_start=5] [countdown_end=15]
Output: <input>_ticking.mp4
"""
import sys, os, wave, subprocess
import numpy as np

SR = 44100

# ---------- core synth helpers ----------
def _adsr(n, attack, tau):
    t = np.arange(n) / SR
    e = np.exp(-t / tau)
    a = max(1, int(attack * SR))
    e[:a] *= np.linspace(0, 1, a)
    return e

def thump(f0, f1, amp, dur):
    """One heart thud: downward pitch-swept sine + a touch of mid body so the
    rhythm still reads on small phone speakers."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.05)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sub = np.sin(ph) * _adsr(n, 0.004, 0.10)
    body = np.sin(2*np.pi*150*t) * _adsr(n, 0.002, 0.045) * 0.25
    out = (sub + body) * amp
    # smooth the tail to true zero so each thud ends cleanly (no click/buzz)
    f = min(int(0.04 * SR), n)
    if f > 0:
        out[-f:] *= np.cos(np.linspace(0, np.pi / 2, f)) ** 2
    return out

def heartbeat(amp=0.7):
    """One beat = lub (S1, low+strong) then dub (S2, softer+higher) ~0.17s later."""
    lub = thump(85, 46, amp, 0.20)
    dub = thump(98, 55, amp * 0.62, 0.16)
    gap = int(0.17 * SR)
    n = gap + len(dub)
    out = np.zeros(n)
    out[:len(lub)] += lub
    out[gap:gap+len(dub)] += dub
    return out

# ---------- convolution reverb (FFT) ----------
def make_ir(decay=0.55, length=1.7, seed=0):
    rng = np.random.default_rng(seed)
    n = int(length * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t / decay)
    ir[: int(0.003 * SR)] = 0  # small pre-delay
    return ir / np.sqrt(np.sum(ir**2))

def conv(x, ir):
    L = len(x) + len(ir) - 1
    nfft = 1 << (L - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)
    return y[:len(x)]

# ---------- build adult track (stereo) ----------
def build_adult(dur, cd_start, cd_end):
    """Heartbeat countdown only: silence, then one lub-dub per second across the
    countdown window. No drone bed, no reveal chord."""
    total = int(dur * SR)
    dry = np.zeros(total)
    secs = int(round(cd_end - cd_start))           # 10 beats

    for i in range(secs):
        hb = heartbeat(amp=0.7)
        pos = int((cd_start + i) * SR)
        end = min(pos + len(hb), total)
        dry[pos:end] += hb[:end - pos]

    # NO convolution reverb: the white-noise impulse response left an audible
    # noisy wash after every beat. A heartbeat reads best fully dry.
    st = np.column_stack([dry, dry])
    peak = np.max(np.abs(st)) or 1.0
    st = st / peak * 0.85
    ft = int(0.5 * SR)                              # tail fade
    st[-ft:] *= np.linspace(1, 0, ft)[:, None]
    return st

def save_wav(path, stereo):
    data = (np.clip(stereo, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'w') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())

def ffprobe_dur(path):
    out = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=nw=1:nk=1", path], capture_output=True, text=True)
    return float(out.stdout.strip())

if __name__ == "__main__":
    vid = sys.argv[1]
    cd_start = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    cd_end   = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0
    dur = ffprobe_dur(vid)
    wav = os.path.splitext(vid)[0] + "_tick.wav"
    save_wav(wav, build_adult(dur, cd_start, cd_end))
    base, ext = os.path.splitext(vid)
    out = base + "_ticking" + ext
    subprocess.run(["ffmpeg","-y","-i",vid,"-i",wav,"-map","0:v:0","-map","1:a:0",
                    "-c:v","copy","-c:a","aac","-b:a","192k","-shortest",out],
                   check=True, capture_output=True)
    os.remove(wav)
    print("SAVED:", out)
