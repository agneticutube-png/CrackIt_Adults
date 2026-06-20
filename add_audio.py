#!/usr/bin/env python3
"""
Audio layer for riddle Shorts (stage 2 of pipeline).

ADULT: silent until the countdown, then a CINEMATIC countdown in the spirit of
the Interstellar "Mountains" ticking pulse -- each second lands as the SAME
deep, reverberant sub-boom with an organ body, over a steady low drone, and a
grand resolve at the answer reveal. Every beat across the count is identical
(no crescendo, no final-beat shimmer). 100% synthesized -> never Content-ID
claimable.

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

def beat(amp=0.55, shimmer=0.0):
    """One deep cinematic pulse: pitch-dropping sub + organ body + transient."""
    dur = 0.9
    n = int(dur * SR)
    t = np.arange(n) / SR
    # sub boom with downward pitch sweep (90 -> 52 Hz)
    f = 52 + (90 - 52) * np.exp(-t / 0.10)
    phase = 2 * np.pi * np.cumsum(f) / SR
    sub = np.sin(phase) * _adsr(n, 0.004, 0.38)
    # organ body: open-fifth stack on A (royal, not sweet)
    body = (np.sin(2*np.pi*110*t) + 0.7*np.sin(2*np.pi*164.81*t)
            + 0.5*np.sin(2*np.pi*220*t) + 0.25*np.sin(2*np.pi*329.6*t))
    body *= 0.32 * _adsr(n, 0.006, 0.24)
    # transient articulation (the "tock" definition)
    click = np.sin(2*np.pi*2300*t) * _adsr(n, 0.0005, 0.010) * 0.18
    sig = (sub + body + click) * amp
    if shimmer > 0:  # dread: high octaves bloom on final beats
        sh = (np.sin(2*np.pi*880*t) + 0.6*np.sin(2*np.pi*1318.5*t))
        sig += sh * _adsr(n, 0.02, 0.5) * shimmer
    return sig

def drone(n_samples, a0=0.10, a1=0.85):
    """Low swelling pad under the countdown (A1 root + fifth + octave)."""
    t = np.arange(n_samples) / SR
    pad = (np.sin(2*np.pi*55*t) + 0.6*np.sin(2*np.pi*82.4*t)
           + 0.4*np.sin(2*np.pi*110*t))
    # slow tremolo for movement + escalating swell
    trem = 1 + 0.10 * np.sin(2*np.pi*0.7*t)
    ramp = np.linspace(a0, a1, n_samples) ** 1.4
    return pad * trem * ramp * 0.16

def resolve_chord(amp=0.34):
    """Grand reverberant resolve when the answer appears (A minor, brightened)."""
    dur = 2.4
    n = int(dur * SR)
    t = np.arange(n) / SR
    chord = (np.sin(2*np.pi*110*t) + 0.7*np.sin(2*np.pi*164.81*t)
             + 0.6*np.sin(2*np.pi*261.63*t) + 0.4*np.sin(2*np.pi*329.6*t)
             + 0.25*np.sin(2*np.pi*523.25*t))
    return chord * _adsr(n, 0.01, 0.9) * amp

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
    total = int(dur * SR)
    dry = np.zeros(total)
    secs = int(round(cd_end - cd_start))           # 10 beats

    for i in range(secs):
        # identical pulse on every second of the countdown (no crescendo, no
        # shimmer on the final beats) so the whole count feels uniform.
        b = beat(amp=0.6, shimmer=0.0)
        pos = int((cd_start + i) * SR)
        end = min(pos + len(b), total)
        dry[pos:end] += b[:end - pos]

    # steady drone bed across the countdown (constant level, not swelling)
    n_cd = int((cd_end - cd_start) * SR)
    dr = drone(n_cd, a0=0.6, a1=0.6)
    p0 = int(cd_start * SR)
    end = min(p0 + n_cd, total)
    dry[p0:end] += dr[:end - p0]

    # grand resolve at the reveal
    rc = resolve_chord()
    pr = int(cd_end * SR)
    end = min(pr + len(rc), total)
    dry[pr:end] += rc[:end - pr]

    # stereo via two slightly different reverb IRs (width + cinematic space)
    irL, irR = make_ir(seed=1), make_ir(seed=2)
    wet = 0.42
    L = dry + wet * conv(dry, irL)
    R = dry + wet * conv(dry, irR)

    st = np.column_stack([L, R])
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
    wav = "/sessions/magical-modest-ramanujan/_tick.wav"
    save_wav(wav, build_adult(dur, cd_start, cd_end))
    base, ext = os.path.splitext(vid)
    out = base + "_ticking" + ext
    subprocess.run(["ffmpeg","-y","-i",vid,"-i",wav,"-map","0:v:0","-map","1:a:0",
                    "-c:v","copy","-c:a","aac","-b:a","192k","-shortest",out],
                   check=True, capture_output=True)
    os.remove(wav)
    print("SAVED:", out)
