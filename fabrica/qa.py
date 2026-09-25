"""Gates de qualidade.

  grade(...)        → folha de contato (masters ou frames) pra VOCÊ olhar antes de gastar vídeo
  gate_clipes(...)  → por clipe: integridade · tamanho · duração · áudio · frame-0 × frame-base
                      (clipe cruzado) · whisper × fala do roteiro (fala errada/inventada)
"""
import json
import os
import tempfile

from PIL import Image, ImageDraw, ImageFont

from . import midia, transcricao

MIN_BYTES = 200_000


def _fonte(tam):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


def grade(itens, destino, colunas=6, largura=220):
    """itens = [(rotulo, caminho_png_ou_None), …] → JPG com as miniaturas rotuladas."""
    alt = int(largura * 16 / 9)
    linhas = max(1, -(-len(itens) // colunas))
    folha = Image.new("RGB", (colunas * largura, linhas * (alt + 28)), (24, 24, 24))
    d = ImageDraw.Draw(folha)
    for i, (rot, p) in enumerate(itens):
        x, y = (i % colunas) * largura, (i // colunas) * (alt + 28)
        if p and os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((largura, alt))
            folha.paste(im, (x + (largura - im.width) // 2, y + 28))
        else:
            d.text((x + 10, y + 60), "FALTA", font=_fonte(22), fill=(220, 80, 80))
        d.text((x + 6, y + 4), rot, font=_fonte(16), fill=(255, 255, 255))
    folha.save(destino, quality=88)
    return destino


def _similaridade_imagem(a, b):
    """Correlação de luminância em 64x114 (0..1). Baixa = o clipe não nasceu daquele frame (clipe cruzado)."""
    import numpy as np
    ia = np.asarray(Image.open(a).convert("L").resize((64, 114)), dtype=float).ravel()
    ib = np.asarray(Image.open(b).convert("L").resize((64, 114)), dtype=float).ravel()
    ia -= ia.mean()
    ib -= ib.mean()
    den = (np.linalg.norm(ia) * np.linalg.norm(ib)) or 1.0
    return float(max(0.0, (ia @ ib) / den))


def checar_clipe(caminho, fala="", frame_base=None, idioma="pt"):
    r = {"clipe": os.path.basename(caminho), "problemas": []}
    if not os.path.exists(caminho):
        r["problemas"].append("arquivo não existe")
        return r
    r["bytes"] = os.path.getsize(caminho)
    if r["bytes"] < MIN_BYTES:
        r["problemas"].append(f"arquivo pequeno demais ({r['bytes']} bytes) — download de erro/HTML?")
    if not midia.integro(caminho):
        r["problemas"].append("ffprobe não abre (corrompido)")
        return r
    r["duracao"] = round(midia.duracao(caminho), 2)
    if r["duracao"] < 3:
        r["problemas"].append(f"curto demais ({r['duracao']}s)")
    if fala and not midia.tem_audio(caminho):
        r["problemas"].append("sem trilha de áudio, mas a cena tem fala")
    if frame_base and os.path.exists(frame_base):
        with tempfile.TemporaryDirectory() as tmp:
            f0 = midia.frame_em(caminho, 0.1, os.path.join(tmp, "f0.png"))
            r["semelhanca_frame"] = round(_similaridade_imagem(f0, frame_base), 3)
        if r["semelhanca_frame"] < 0.5:
            r["problemas"].append(f"frame 0 não bate com o frame-base ({r['semelhanca_frame']}) — clipe cruzado/errado?")
    if fala:
        ws = transcricao.palavras(caminho, idioma)
        if ws is not None:
            ouvido = " ".join(w for w, _, _ in ws)
            r["transcricao"] = ouvido
            r["similaridade_fala"] = round(transcricao.similaridade(fala, ouvido), 3)
            n_rot, n_ouv = len(transcricao.normaliza(fala)), len(transcricao.normaliza(ouvido))
            if r["similaridade_fala"] < 0.60:
                r["problemas"].append(f"fala não bate com o roteiro (dice {r['similaridade_fala']})")
            elif n_ouv > n_rot * 1.25 + 2:
                r["problemas"].append(f"fala INVENTADA: {n_ouv} palavras ouvidas × {n_rot} no roteiro (o corte apara o excesso do fim)")
    r["aprovado"] = not r["problemas"]
    return r


def gate_clipes(leva, pastas, so=None):
    resultado = {}
    for ad in leva["ads"]:
        if so and ad["id"] not in so:
            continue
        for c in ad["cenas"]:
            resultado[c["chave"]] = checar_clipe(pastas.clipe(c["chave"]), c.get("fala", ""), pastas.frame(c["chave"]),
                                                 leva["idioma"])
    with open(os.path.join(pastas.qa, "GATE-CLIPES.json"), "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
    return resultado


def grade_masters(leva, pastas):
    usadas = sorted({c["persona"] for ad in leva["ads"] for c in ad["cenas"] if c.get("usa_master")})
    return grade([(pk, pastas.master(pk)) for pk in usadas], os.path.join(pastas.qa, "GRADE-MASTERS.jpg"))


def grade_frames(leva, pastas, so=None):
    itens = []
    for ad in leva["ads"]:
        if so and ad["id"] not in so:
            continue
        itens += [(f"{c['chave']} {c.get('tipo') or ''}", pastas.frame(c["chave"])) for c in ad["cenas"]]
    return grade(itens, os.path.join(pastas.qa, "GRADE-FRAMES.jpg"), colunas=8, largura=180)
