"""Transcrição com timestamps por palavra (opcional).

Usa, nesta ordem: faster-whisper (pip install faster-whisper) ou whisper.cpp
(`whisper-cli` + WHISPER_MODEL=/caminho/ggml-small.bin). Sem nenhum dos dois o
pipeline continua: o corte vira por silêncio e a legenda é distribuída por proporção.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata

from . import midia

_modelo = None


def disponivel():
    return _backend() is not None


def _backend():
    if os.environ.get("SEM_WHISPER"):
        return None
    try:
        import faster_whisper  # noqa: F401
        return "faster"
    except ImportError:
        pass
    if shutil.which("whisper-cli") and os.environ.get("WHISPER_MODEL"):
        return "cpp"
    return None


def palavras(path, idioma="pt"):
    """[(palavra, inicio, fim), …] ou None se não há whisper instalado."""
    b = _backend()
    if b == "faster":
        return _faster(path, idioma)
    if b == "cpp":
        return _cpp(path, idioma)
    return None


def _carregar_modelo(device):
    from faster_whisper import WhisperModel
    return WhisperModel(os.environ.get("WHISPER_TAMANHO", "small"), device=device, compute_type="int8")


def _faster(path, idioma):
    """WHISPER_DEVICE=auto|cpu|cuda (default auto). Com placa NVIDIA mas sem as DLLs do CUDA
    (cublas/cudnn), o erro só aparece na transcrição: aí cai para CPU e segue."""
    global _modelo
    if _modelo is None:
        _modelo = _carregar_modelo(os.environ.get("WHISPER_DEVICE", "auto"))
    try:
        segs, _ = _modelo.transcribe(path, language=idioma, word_timestamps=True, vad_filter=False)
        return [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or []) if w.word.strip()]
    except RuntimeError as e:
        if not any(k in str(e).lower() for k in ("cublas", "cudnn", "cuda")):
            raise
        print("  (whisper: GPU sem bibliotecas CUDA — usando CPU)", flush=True)
        _modelo = _carregar_modelo("cpu")
        segs, _ = _modelo.transcribe(path, language=idioma, word_timestamps=True, vad_filter=False)
        return [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or []) if w.word.strip()]


def _cpp(path, idioma):
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        # 0,5s de silêncio na frente: sem isso as primeiras palavras de quem fala no segundo zero somem
        midia.run(["-i", path, "-af", "adelay=500|500", "-ar", "16000", "-ac", "1", wav])
        base = os.path.join(tmp, "out")
        subprocess.run(["whisper-cli", "-m", os.environ["WHISPER_MODEL"], "-l", idioma, "-ml", "1", "-ojf", "-of", base, wav],
                       capture_output=True, text=True)
        try:
            with open(base + ".json", encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, ValueError):
            return None
    out = []
    for seg in dados.get("transcription", []):
        txt = seg.get("text", "").strip()
        if not txt or txt.startswith("["):
            continue
        a = seg["offsets"]["from"] / 1000 - 0.5
        b = seg["offsets"]["to"] / 1000 - 0.5
        out.append((txt, max(0.0, a), max(0.0, b)))
    return out


NUMEROS = {"zero": "0", "um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "quatro": "4", "cinco": "5",
           "seis": "6", "sete": "7", "oito": "8", "nove": "9", "dez": "10", "onze": "11", "doze": "12", "quinze": "15",
           "vinte": "20", "trinta": "30", "quarenta": "40", "cinquenta": "50", "sessenta": "60", "cem": "100"}


def normaliza(txt):
    txt = unicodedata.normalize("NFKD", txt.lower())
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    toks = re.findall(r"\w+", txt)
    return [NUMEROS.get(t, t) for t in toks]


def similaridade(a, b):
    """Dice de bigramas de palavras (0..1). < 0,60 = clipe com a fala de OUTRA cena."""
    ta, tb = normaliza(a), normaliza(b)
    ba = {tuple(ta[i:i + 2]) for i in range(len(ta) - 1)} or {tuple(ta)}
    bb = {tuple(tb[i:i + 2]) for i in range(len(tb) - 1)} or {tuple(tb)}
    if not ta or not tb:
        return 0.0
    return 2 * len(ba & bb) / (len(ba) + len(bb))
