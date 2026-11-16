#!/usr/bin/env python3
"""
Pipeline de tratamento de áudio (redução de ruído, brilho/clareza e equilíbrio de volume)
preservando o timbre natural da voz.

Dependências:
    pip install numpy scipy

Uso:
    python3 tratar_audio.py AUDIO-2026-11-15-08-36-43.m4a
    python3 tratar_audio.py entrada.m4a -o saida_tratado.m4a
"""

import argparse
import math
import os
import subprocess
import sys
import tempfile
import wave

try:
    import numpy as np
    from scipy.signal import lfilter
except ImportError:
    print(
        "Erro: este script requer 'numpy' e 'scipy'.\n"
        "Instale com: pip3 install numpy scipy",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Filtros Biquad (Audio EQ Cookbook)
# ---------------------------------------------------------------------------

def biquad_hpf(fs: float, f0: float, q: float = 0.7071):
    w0 = 2.0 * math.pi * f0 / fs
    alpha = math.sin(w0) / (2.0 * q)
    cw = math.cos(w0)
    a0 = 1.0 + alpha
    b = np.array([(1.0 + cw) / 2.0, -(1.0 + cw), (1.0 + cw) / 2.0]) / a0
    a = np.array([1.0, -2.0 * cw / a0, (1.0 - alpha) / a0])
    return b, a


def biquad_peaking(fs: float, f0: float, gain_db: float, q: float):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / fs
    alpha = math.sin(w0) / (2.0 * q)
    cw = math.cos(w0)
    a0 = 1.0 + alpha / A
    b = np.array([1.0 + alpha * A, -2.0 * cw, 1.0 - alpha * A]) / a0
    a = np.array([1.0, -2.0 * cw / a0, (1.0 - alpha / A) / a0])
    return b, a


def biquad_highshelf(fs: float, f0: float, gain_db: float, s: float = 0.7):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / fs
    cw = math.cos(w0)
    sw = math.sin(w0)
    alpha = (sw / 2.0) * math.sqrt((A + 1.0 / A) * (1.0 / s - 1.0) + 2.0)
    sq_a2a = 2.0 * math.sqrt(A) * alpha
    a0 = (A + 1.0) - (A - 1.0) * cw + sq_a2a
    b = np.array([
        A * ((A + 1.0) + (A - 1.0) * cw + sq_a2a),
        -2.0 * A * ((A - 1.0) + (A + 1.0) * cw),
        A * ((A + 1.0) + (A - 1.0) * cw - sq_a2a),
    ]) / a0
    a = np.array([
        1.0,
        2.0 * ((A - 1.0) - (A + 1.0) * cw) / a0,
        ((A + 1.0) - (A - 1.0) * cw - sq_a2a) / a0,
    ])
    return b, a


# ---------------------------------------------------------------------------
# Etapas de Processamento DSP
# ---------------------------------------------------------------------------

def stft_noise_reduction(
    audio: np.ndarray,
    n_fft: int = 2048,
    hop: int = 512,
    g_min: float = 0.25,
    over_sub: float = 1.4,
) -> np.ndarray:
    """Redução espectral de ruído (Wiener suave, estéreo linkado)."""
    nframes, nch = audio.shape
    win = np.hanning(n_fft + 1)[:-1]
    # Fator COLA para Hann com overlap 75% (hop = n_fft / 4): sum(win^2) = 1.5
    ola_scale = 1.0 / 1.5

    nstft = (nframes - n_fft) // hop + 1 if nframes >= n_fft else 0
    if nstft == 0:
        return audio.copy()

    # Estima energia por frame (canal mono médio)
    mono = audio.mean(axis=1)
    # Uma visão por janelas evita materializar duas matrizes do tamanho
    # de quatro gravações inteiras durante a seleção dos trechos silenciosos.
    frames_mono = np.lib.stride_tricks.sliding_window_view(mono, n_fft)[::hop]
    energies = np.einsum("ij,ij->i", frames_mono, frames_mono) / n_fft
    order = np.argsort(energies)
    k_start = int(nstft * 0.02)
    k_end = max(k_start + 1, int(nstft * 0.08))
    quiet_frames = frames_mono[order[k_start:k_end]] * win[None, :]
    noise_spec = np.fft.rfft(quiet_frames, axis=1)
    noise_psd = np.mean(np.abs(noise_spec) ** 2, axis=0)

    out = np.zeros_like(audio)
    smooth_pwr = np.zeros(n_fft // 2 + 1, dtype=np.float64)

    for f in range(nstft):
        pos = f * hop
        seg_l = audio[pos : pos + n_fft, 0] * win
        seg_r = audio[pos : pos + n_fft, 1] * win if nch > 1 else seg_l

        spec_l = np.fft.rfft(seg_l)
        spec_r = np.fft.rfft(seg_r)

        pwr = 0.5 * (np.abs(spec_l) ** 2 + np.abs(spec_r) ** 2)
        smooth_pwr = 0.45 * smooth_pwr + 0.55 * pwr

        np_thr = noise_psd * over_sub
        gain = np.where(smooth_pwr > np_thr, (smooth_pwr - np_thr) / (smooth_pwr + 1e-18), 0.0)
        gain = np.maximum(np.sqrt(gain), g_min)

        # Suavização espectral entre bins vizinhos para evitar "musical noise"
        gain_sm = gain.copy()
        gain_sm[1:-1] = 0.2 * gain[:-2] + 0.6 * gain[1:-1] + 0.2 * gain[2:]

        rec_l = np.fft.irfft(spec_l * gain_sm, n=n_fft) * win * ola_scale
        out[pos : pos + n_fft, 0] += rec_l
        if nch > 1:
            rec_r = np.fft.irfft(spec_r * gain_sm, n=n_fft) * win * ola_scale
            out[pos : pos + n_fft, 1] += rec_r

    return out


def apply_eq(audio: np.ndarray, sr: float, extra_brightness: float = 0.0) -> np.ndarray:
    """Equalização preservando o timbre: HPF 70 Hz, corte 280 Hz, presença 3.5 kHz, ar 9 kHz."""
    filters = [
        biquad_hpf(sr, 70.0, q=0.7071),
        biquad_peaking(sr, 280.0, gain_db=-1.5, q=1.0),
        biquad_peaking(sr, 3500.0, gain_db=+2.5, q=0.85),
        biquad_highshelf(sr, 9000.0, gain_db=3.5 + extra_brightness, s=0.7),
    ]
    out = audio.copy()
    for b, a in filters:
        for ch in range(out.shape[1]):
            out[:, ch] = lfilter(b, a, out[:, ch])
    return out


def balance_dynamics(audio: np.ndarray, sr: float) -> np.ndarray:
    """Nivelador lento (AGC) + Compressor soft-knee + Normalização ativa + Limitador lookahead."""
    nframes, nch = audio.shape

    # 1. Nivelador lento (AGC em blocos de 10 ms para performance em Python)
    blk = max(1, int(0.010 * sr))
    nblks = nframes // blk
    rms_alpha = math.exp(-blk / (0.8 * sr))
    agc_alpha = math.exp(-blk / (1.2 * sr))
    att_c = math.exp(-blk / (0.015 * sr))
    rel_c = math.exp(-blk / (0.180 * sr))

    thresh, ratio, knee = -20.0, 2.5, 6.0
    rms_env = 1e-6
    agc_gain = 1.0
    comp_env = 0.0

    gains = np.ones(nblks, dtype=np.float64)
    for k in range(nblks):
        seg = audio[k * blk : (k + 1) * blk]
        p = float(np.mean(seg ** 2))
        rms_env = rms_alpha * rms_env + (1.0 - rms_alpha) * p
        rms_db = 10.0 * math.log10(rms_env + 1e-18)

        target_agc_db = 0.0
        if rms_db > -42.0:
            target_agc_db = max(-4.0, min(6.0, -21.0 - rms_db))
        agc_gain = agc_alpha * agc_gain + (1.0 - agc_alpha) * (10.0 ** (target_agc_db / 20.0))

        peak = float(np.max(np.abs(seg))) * agc_gain
        c_coef = att_c if peak > comp_env else rel_c
        comp_env = c_coef * comp_env + (1.0 - c_coef) * peak
        env_db = 20.0 * math.log10(comp_env + 1e-12)

        if 2.0 * (env_db - thresh) < -knee:
            gr_db = 0.0
        elif 2.0 * abs(env_db - thresh) <= knee:
            x = env_db - thresh + knee / 2.0
            gr_db = (1.0 / ratio - 1.0) * (x * x) / (2.0 * knee)
        else:
            gr_db = (1.0 / ratio - 1.0) * (env_db - thresh)

        gains[k] = agc_gain * (10.0 ** (gr_db / 20.0))

    # Interpola ganho por amostra para evitar degraus
    sample_idx = np.arange(nframes) / blk
    blk_centers = np.arange(nblks) + 0.5
    gain_curve = np.interp(sample_idx, blk_centers, gains)[:, None]
    out = audio * gain_curve

    # 2. Normalização de RMS ativo para -16.5 dBFS
    blk100 = int(0.1 * sr)
    n100 = nframes // blk100
    if n100 > 0:
        segs = out[: n100 * blk100].reshape(n100, blk100, nch)
        blk_pwr = np.mean(segs ** 2, axis=(1, 2))
        active = blk_pwr[10.0 * np.log10(blk_pwr + 1e-18) > -40.0]
        active_rms_db = 10.0 * math.log10((float(np.mean(active)) if len(active) else 1e-6) + 1e-18)
        makeup_db = min(12.0, -16.5 - active_rms_db)
        print(f"RMS ativo antes do makeup: {active_rms_db:.2f} dBFS | Makeup: {makeup_db:+.2f} dB")
        out *= 10.0 ** (makeup_db / 20.0)

    # 3. Limitador lookahead (-1.0 dBFS)
    ceiling = 10.0 ** (-1.0 / 20.0)  # 0.89125
    look = int(0.005 * sr)
    abs_peak = np.max(np.abs(out), axis=1)
    # Máximo deslizante futuro (lookahead) via blocos de 1 ms para rapidez
    step = max(1, int(0.001 * sr))
    lim_rel = math.exp(-step / (0.060 * sr))
    lim_gain = 1.0
    nsteps = (nframes + step - 1) // step
    step_gains = np.ones(nsteps, dtype=np.float64)
    for s_idx in range(nsteps):
        i0 = s_idx * step
        i1 = min(nframes, i0 + look + step)
        pk = float(np.max(abs_peak[i0:i1]))
        req = ceiling / pk if pk > ceiling else 1.0
        lim_gain = req if req < lim_gain else lim_rel * lim_gain + (1.0 - lim_rel) * req
        step_gains[s_idx] = lim_gain

    lim_curve = np.interp(np.arange(nframes) / step, np.arange(nsteps) + 0.5, step_gains)[:, None]
    out *= lim_curve
    np.clip(out, -ceiling, ceiling, out=out)
    return out


# ---------------------------------------------------------------------------
# I/O (afconvert no macOS + WAV)
# ---------------------------------------------------------------------------

def decode_to_wav(src: str, dst_wav: str) -> None:
    if src.lower().endswith(".wav"):
        import shutil
        shutil.copyfile(src, dst_wav)
        return
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16", src, dst_wav],
        check=True,
    )


def encode_from_wav(src_wav: str, dst_m4a: str, bitrate: int = 192000) -> None:
    import imageio_ffmpeg

    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-i", src_wav,
         "-c:a", "aac", "-b:a", str(bitrate), dst_m4a],
        check=True,
    )


def read_wav(path: str):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        nframes = w.getnframes()
        raw = w.readframes(nframes)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    return data.reshape(-1, nch), sr


def write_wav(path: str, audio: np.ndarray, sr: int) -> None:
    rng = np.random.default_rng(42)
    dither = rng.uniform(-0.5, 0.5, audio.shape) + rng.uniform(-0.5, 0.5, audio.shape)
    pcm = np.clip(np.rint(audio * 32767.0 + dither), -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(audio.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    parser = argparse.ArgumentParser(description="Tratamento de áudio preservando o timbre.")
    parser.add_argument("entrada", help="Arquivo de áudio de entrada (.m4a, .wav, etc.)")
    parser.add_argument("-o", "--saida", help="Arquivo de saída .m4a (padrão: <entrada>_tratado.m4a)")
    parser.add_argument("--brilho-adicional", type=float, default=0.0)
    args = parser.parse_args()

    src = os.path.abspath(args.entrada)
    if args.saida:
        dst = os.path.abspath(args.saida)
    else:
        base, _ = os.path.splitext(src)
        dst = f"{base}_tratado.m4a"

    with tempfile.TemporaryDirectory() as tmp:
        in_wav = os.path.join(tmp, "in.wav")
        out_wav = os.path.join(tmp, "out.wav")

        print(f"1/5 Decodificando {os.path.basename(src)}...")
        decode_to_wav(src, in_wav)
        audio, sr = read_wav(in_wav)

        print("2/5 Aplicando redução espectral de ruído (STFT/Wiener)...")
        audio = stft_noise_reduction(audio)

        print("3/5 Aplicando equalização para brilho e clareza...")
        audio = apply_eq(audio, sr, args.brilho_adicional)

        print("4/5 Equilibrando volume e dinâmica...")
        audio = balance_dynamics(audio, sr)

        print(f"5/5 Codificando saída em {os.path.basename(dst)}...")
        write_wav(out_wav, audio, sr)
        encode_from_wav(out_wav, dst)

    print(f"Concluído: {dst}")


if __name__ == "__main__":
    main()

