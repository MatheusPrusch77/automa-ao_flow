"""Gate de RITMO medido: vídeo parado é vídeo reprovado, e ritmo se mede — não se sente.

  trocas de estímulo por minuto (detecção de cena, limiar 0,05) · maior plano sem troca ·
  silêncios > 0,3s a -25dB · diferença de duração vídeo × áudio

Réguas (calibradas no pacote de origem): criativo ≥ 10 trocas/min e maior plano ≤ 9s;
VSL ≥ 12/min e ≤ 12s."""
import re
import subprocess

from . import midia

REGUAS = {"criativo": (10.0, 9.0), "vsl": (12.0, 12.0)}


def cortes(path, limiar=0.05):
    r = subprocess.run([midia.FFMPEG, "-hide_banner", "-i", path, "-vf", f"select='gt(scene,{limiar})',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    return sorted({round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)})


def medir(path, modo="criativo", limiar=0.05):
    info = midia.probe(path)
    dur = float(info["format"]["duration"])
    dv = next((float(s.get("duration", dur)) for s in info["streams"] if s["codec_type"] == "video"), dur)
    da = next((float(s.get("duration", dur)) for s in info["streams"] if s["codec_type"] == "audio"), 0.0)
    cs = cortes(path, limiar)
    marcos = [0.0] + cs + [dur]
    planos = [(marcos[i + 1] - marcos[i], marcos[i]) for i in range(len(marcos) - 1)]
    maior, onde = max(planos) if planos else (dur, 0.0)
    sil = midia.silencios(path, "-25dB", 0.3)
    min_trocas, max_plano = REGUAS[modo]
    trocas_min = len(cs) / (dur / 60) if dur else 0
    problemas = []
    if trocas_min < min_trocas:
        problemas.append(f"{trocas_min:.1f} trocas/min (< {min_trocas})")
    if maior > max_plano:
        problemas.append(f"plano parado de {maior:.1f}s em {onde:.1f}s (> {max_plano}s)")
    if sil:
        problemas.append(f"{len(sil)} silêncio(s) > 0,3s (1º em {sil[0][0]:.1f}s)")
    if da and abs(dv - da) > 1.5:
        problemas.append(f"vídeo×áudio diferem {abs(dv - da):.1f}s")
    return {"arquivo": path, "duracao": round(dur, 1), "trocas_por_min": round(trocas_min, 1), "maior_plano": round(maior, 1),
            "maior_plano_em": round(onde, 1), "silencios": len(sil), "aprovado": not problemas, "problemas": problemas}
