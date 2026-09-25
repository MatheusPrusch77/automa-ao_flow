"""Utilitários de ffmpeg/ffprobe."""
import json
import os
import re
import shutil
import subprocess

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "ffprobe"
W, H, FPS = 1080, 1920, 24


class ErroMidia(RuntimeError):
    pass


def run(args, quiet=True):
    cmd = [FFMPEG, "-y", "-hide_banner"] + (["-loglevel", "error"] if quiet else []) + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroMidia(f"ffmpeg falhou ({r.returncode}): {' '.join(cmd)[:400]}\n{r.stderr[-1500:]}")
    return r


def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroMidia(f"ffprobe não abriu {path}: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def duracao(path):
    return float(probe(path)["format"]["duration"])


def tem_audio(path):
    return any(s["codec_type"] == "audio" for s in probe(path)["streams"])


def dims(path):
    v = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
    return int(v["width"]), int(v["height"])


def integro(path):
    try:
        probe(path)
        return True
    except ErroMidia:
        return False


def tem_libass():
    r = subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True)
    return re.search(r"\sass\s", r.stdout) is not None


def silencios(path, noise="-25dB", minimo=0.3):
    """Lista de (inicio, fim) de silêncios no áudio."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-af", f"silencedetect=noise={noise}:d={minimo}",
                        "-f", "null", "-"], capture_output=True, text=True)
    ini = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    fim = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    if len(fim) < len(ini):
        fim.append(duracao(path))
    return [(max(0.0, a), b) for a, b in zip(ini, fim)]


def normalizar(src, dst, inicio=0.0, fim=None, crop_wm=False):
    """Corta [inicio, fim], cobre 1080x1920 (crop-to-cover, nunca estica), 24fps, yuv420p, AAC 48k estéreo.
    Clipe sem áudio ganha trilha silenciosa, pra concat por filtro não quebrar."""
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if crop_wm:  # o gerador assina o canto: zoom leve de 6% remove a marca
        vf = f"scale={int(W * 1.06)}:{int(H * 1.06)}:force_original_aspect_ratio=increase,crop={W}:{H}"
    vf += f",fps={FPS},setsar=1,format=yuv420p"
    args = ["-ss", f"{inicio:.3f}"] + (["-to", f"{fim:.3f}"] if fim else []) + ["-i", src]
    if tem_audio(src):
        args += ["-vf", vf, "-af", "aresample=48000,aformat=channel_layouts=stereo", "-map", "0:v:0", "-map", "0:a:0"]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    run(args + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", dst])
    return dst


def cortar_intervalos(src, dst, manter):
    """Mantém só os intervalos [(a,b), …] (vídeo e áudio juntos)."""
    if not manter:
        raise ErroMidia(f"nada a manter em {src}")
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in manter)
    run(["-i", src, "-vf", f"select='{expr}',setpts=N/FRAME_RATE/TB", "-af", f"aselect='{expr}',asetpts=N/SR/TB",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", dst])
    return dst


def frame_em(src, t, dst):
    run(["-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", dst])
    return dst
