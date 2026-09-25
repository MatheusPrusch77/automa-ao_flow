"""Montagem final de cada ad:

  por clipe: corte do silêncio/fade do fim (whisper ou silencedetect) → 1080x1920/24fps →
             remove silêncio interno > 0,3s a -25dB → punch-in (zoom 1,12 na 2ª metade) nos clipes do corpo > 4,6s
  gancho:    SPLIT (pessoa em cima + insert embaixo) · INSERT_PRIMEIRO (1,6s de insert e a pessoa entra falando)
  ad:        concat por filtro → legenda ASS com o texto do ROTEIRO (whisper só dá o tempo) →
             faixa de headline (opcional) → pílula de CTA nos últimos segundos → checagem de integridade
"""
import os
import re
from dataclasses import dataclass

from . import banner, midia, transcricao
from .midia import FPS, H, W


@dataclass
class Opcoes:
    punch_in: bool = True
    punch_min: float = 4.6
    punch_z: float = 1.12
    aparar: bool = True
    legenda: bool = True
    headline: bool = True
    cta: bool = True
    cta_seg: float = 8.0
    crop_wm: bool = False
    min_dur: float = 60.0
    insert_seg: float = 1.6
    palavras_tela: tuple = ()  # frases que saltam na tela quando são faladas (ex.: "soda", "follow me")
    palavras_tela_so_final: bool = False  # só na última cena (o CTA), não a cada menção no vídeo

    @classmethod
    def da_leva(cls, cfg):
        campos = {k: v for k, v in (cfg or {}).items() if k in cls.__dataclass_fields__}
        if "palavras_tela" in campos:
            campos["palavras_tela"] = tuple(campos["palavras_tela"])
        return cls(**campos)


def _fim_da_fala(src, idioma):
    """(inicio, fim) útil do clipe cru: corta a espera antes da fala e o silêncio/fade do final."""
    dur = midia.duracao(src)
    ws = transcricao.palavras(src, idioma)
    if ws:
        return max(0.0, ws[0][1] - 0.08), min(dur, ws[-1][2] + 0.18)
    sil = midia.silencios(src, "-30dB", 0.25)
    ini, fim = 0.0, dur
    if sil and sil[0][0] <= 0.05 and sil[0][1] < 1.5:
        ini = max(0.0, sil[0][1] - 0.08)
    if sil and sil[-1][1] >= dur - 0.1 and sil[-1][0] > ini + 1.0:
        fim = sil[-1][0] + 0.15
    return ini, fim


def _sem_silencio_interno(src, dst, noise="-25dB", minimo=0.3, respiro=0.08):
    dur = midia.duracao(src)
    sil = [(a, b) for a, b in midia.silencios(src, noise, minimo) if b - a > minimo]
    if not sil:
        return src
    manter, cursor = [], 0.0
    for a, b in sil:
        if a + respiro > cursor:
            manter.append((cursor, a + respiro))
        cursor = max(cursor, b - respiro)
    if cursor < dur:
        manter.append((cursor, dur))
    manter = [(a, b) for a, b in manter if b - a > 0.12]
    return midia.cortar_intervalos(src, dst, manter)


def punch_in(src, dst, z=1.12):
    d = midia.duracao(src)
    meio = d / 2
    cw, ch = int(W / z) // 2 * 2, int(H / z) // 2 * 2
    fc = (f"[0:v]trim=0:{meio:.3f},setpts=PTS-STARTPTS[a];"
          f"[0:v]trim={meio:.3f},setpts=PTS-STARTPTS,crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})*0.30,scale={W}:{H},setsar=1[b];"
          f"[a][b]concat=n=2:v=1:a=0,format=yuv420p[v]")
    midia.run(["-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "18", "-c:a", "copy", dst])
    return dst


def gancho_split(pessoa, insert, dst, topo=1150):
    base = H - topo
    fc = (f"[0:v]crop={W}:{topo}:0:0[t];"
          f"[1:v]crop={W}:{base}:0:(ih-{base})/2,tpad=stop_mode=clone:stop_duration=30[b];"
          f"[t][b]vstack=inputs=2,format=yuv420p[v]")
    midia.run(["-i", pessoa, "-i", insert, "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-t",
               f"{midia.duracao(pessoa):.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", dst])
    return dst


def gancho_insert_primeiro(insert, pessoa, dst, seg=1.6, vol=0.25):
    fc = (f"[0:v]trim=0:{seg},setpts=PTS-STARTPTS[iv];[0:a]atrim=0:{seg},asetpts=PTS-STARTPTS,volume={vol}[ia];"
          f"[iv][ia][1:v][1:a]concat=n=2:v=1:a=1[v][a]")
    midia.run(["-i", insert, "-i", pessoa, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", dst])
    return dst


def concat(partes, dst):
    ins, fc = [], ""
    for i, p in enumerate(partes):
        ins += ["-i", p]
        fc += f"[{i}:v]fps={FPS},scale={W}:{H},setsar=1,format=yuv420p[v{i}];[{i}:a]aresample=48000[a{i}];"
    fc += "".join(f"[v{i}][a{i}]" for i in range(len(partes))) + f"concat=n={len(partes)}:v=1:a=1[v][a]"
    midia.run(ins + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
                     "-crf", "18", "-c:a", "aac", "-b:a", "192k", dst])
    return dst


# ── legendas ────────────────────────────────────────────────────────────────
def blocos_legenda(fala, max_palavras=4):
    """Blocos de 3-4 palavras, quebrando em pontuação quando possível."""
    toks = fala.split()
    blocos, atual = [], []
    for t in toks:
        atual.append(t)
        if len(atual) >= max_palavras or (len(atual) >= 2 and re.search(r"[.,!?;:]$", t)):
            blocos.append(atual)
            atual = []
    if atual:
        if blocos and len(atual) == 1:
            blocos[-1] += atual
        else:
            blocos.append(atual)
    return [" ".join(b) for b in blocos]


def tempos_legenda(fala, ini, fim, palavras_whisper=None):
    """[(texto, t0, t1)] relativos ao segmento. Com whisper: cada bloco começa na palavra correspondente."""
    blocos = blocos_legenda(fala)
    if not blocos:
        return []
    n_rot = len(fala.split())
    out, acum = [], 0
    if palavras_whisper:
        n_w = len(palavras_whisper)
        for b in blocos:
            k = min(n_w - 1, round(acum * n_w / n_rot))
            out.append([b, palavras_whisper[k][1]])
            acum += len(b.split())
    else:
        total = sum(len(b) for b in blocos)
        t = ini
        for b in blocos:
            out.append([b, t])
            t += (fim - ini) * len(b) / total
    res = []
    for i, (b, t0) in enumerate(out):
        t1 = out[i + 1][1] if i + 1 < len(out) else fim
        res.append((b, max(0.0, t0), max(t0 + 0.3, t1)))
    return res


def tempo_de_frase(fala, frase, ini, fim, palavras_whisper=None):
    """(t0, t1) de quando a frase é dita no segmento, ou None se ela não está na fala."""
    alvo = transcricao.normaliza(frase)
    if not alvo or " ".join(alvo) not in " ".join(transcricao.normaliza(fala)):
        return None
    if palavras_whisper:
        toks = [(transcricao.normaliza(w) or [""])[0] for w, _, _ in palavras_whisper]
        for i in range(len(toks) - len(alvo) + 1):
            if toks[i:i + len(alvo)] == alvo:
                return palavras_whisper[i][1], palavras_whisper[i + len(alvo) - 1][2]
    baixa = fala.lower()
    pos = baixa.find(frase.lower())
    if pos < 0:
        return None
    t0 = ini + (fim - ini) * pos / len(fala)
    return t0, t0 + (fim - ini) * len(frase) / len(fala)


def _ass_t(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def escrever_ass(eventos, destino, fonte="DejaVu Sans", tam=66, margem_v=560):
    cab = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
           "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
           "MarginV, Encoding\n"
           f"Style: Leg,{fonte},{tam},&H0000FFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,{margem_v},1\n"
           f"Style: Destaque,{fonte},118,&H0000FFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,2,0,1,8,3,2,60,60,700,1\n\n"
           "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(cab)
        for ev in eventos:
            txt, a, b = ev[:3]
            estilo = ev[3] if len(ev) > 3 else "Leg"
            txt = txt.replace("{", "(").replace("}", ")")
            if estilo == "Destaque":  # entra com um "pop" (130% → 100%)
                txt = "{\\fscx130\\fscy130\\t(0,140,\\fscx100\\fscy100)}" + txt
            f.write(f"Dialogue: 0,{_ass_t(a)},{_ass_t(b)},{estilo},,0,0,0,,{txt}\n")
    return destino


def _fonte_ass():
    return "Arial" if os.path.exists("/Library/Fonts/Arial.ttf") or os.name == "nt" else "DejaVu Sans"


# ── o ad inteiro ─────────────────────────────────────────────────────────────
def montar_ad(ad, pastas, idioma="pt", opcoes=None, indice=0, log=print):
    op = opcoes or Opcoes()
    wk = os.path.join(pastas.trabalho, ad["id"])
    os.makedirs(wk, exist_ok=True)
    cenas = ad["cenas"]
    faltando = [c["chave"] for c in cenas if not os.path.exists(pastas.clipe(c["chave"]))]
    if faltando:
        raise midia.ErroMidia(f"{ad['id']}: faltam clipes {', '.join(faltando)}")

    def preparar(c, cortar_fala=True):
        src = pastas.clipe(c["chave"])
        base = os.path.join(wk, c["chave"])
        ini, fim = _fim_da_fala(src, idioma) if (cortar_fala and c.get("fala")) else (0.0, None)
        p = midia.normalizar(src, base + "_n.mp4", ini, fim, op.crop_wm)
        if op.aparar and c.get("fala"):
            p = _sem_silencio_interno(p, base + "_s.mp4")
        return p

    insert = next((c for c in cenas if c.get("insert_gancho")), None)
    segmentos = []  # (arquivo, fala, deslocamento_da_fala)
    for c in cenas:
        if c.get("insert_gancho"):
            continue
        p = preparar(c)
        desloc = 0.0
        if c.get("gancho") and insert:
            pi = preparar(insert, cortar_fala=False)
            if ad["mecanica"] == "SPLIT":
                p = gancho_split(p, pi, os.path.join(wk, "gancho_split.mp4"))
            elif ad["mecanica"] == "INSERT_PRIMEIRO":
                p = gancho_insert_primeiro(pi, p, os.path.join(wk, "gancho_insert.mp4"), op.insert_seg)
                desloc = op.insert_seg
        elif not c.get("gancho") and op.punch_in and midia.duracao(p) > op.punch_min:
            p = punch_in(p, os.path.join(wk, c["chave"] + "_p.mp4"), op.punch_z)
        segmentos.append((p, c.get("fala", ""), desloc))

    cat = concat([s[0] for s in segmentos], os.path.join(wk, "concat.mp4"))
    dur_total = midia.duracao(cat)

    eventos, t = [], 0.0
    if op.legenda or op.palavras_tela:
        for i_seg, (arq, fala, desloc) in enumerate(segmentos):
            d = midia.duracao(arq)
            if fala:
                ws = transcricao.palavras(arq, idioma)
                if ws and desloc:
                    ws = [w for w in ws if w[1] >= desloc - 0.1]
                if op.legenda:
                    for txt, a, b in tempos_legenda(fala, desloc, d - 0.05, ws or None):
                        eventos.append((txt, t + a, min(t + b, t + d)))
                ultima = i_seg == len(segmentos) - 1
                for frase in (op.palavras_tela if ultima or not op.palavras_tela_so_final else ()):  # keyword >= 0,9s na tela
                    tf = tempo_de_frase(fala, frase, desloc, d - 0.05, ws or None)
                    if tf:
                        eventos.append((frase.upper(), t + tf[0], min(t + d, max(t + tf[1] + 0.3, t + tf[0] + 0.9)), "Destaque"))
            t += d

    ins, filtros, entrada, n = ["-i", cat], [], "[0:v]", 1
    if eventos:
        ass = escrever_ass(eventos, os.path.join(wk, "legenda.ass"), _fonte_ass())
        ass_esc = ass.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        filtros.append(f"{entrada}ass='{ass_esc}'[v{n}]")
        entrada = f"[v{n}]"
    if op.headline and ad.get("headline"):
        estilo = ad.get("header_estilo") or banner.ROTACAO[(indice // 3) % len(banner.ROTACAO)]
        png, _ = banner.headline(ad["headline"], estilo, os.path.join(wk, "headline.png"))
        ins += ["-i", png]
        filtros.append(f"{entrada}[{n}:v]overlay=0:90[o{n}]")
        entrada = f"[o{n}]"
        n += 1
    if op.cta and ad.get("cta"):
        png, alt = banner.cta(ad["cta"], os.path.join(wk, "cta.png"))
        t0, y = max(0.0, dur_total - op.cta_seg), 1520
        ins += ["-loop", "1", "-i", png]
        filtros.append(f"{entrada}[{n}:v]overlay=x=0:y='if(lt(t,{t0}+0.35),{H}-({H}-{y})*(t-{t0})/0.35,{y}+10*sin(2*PI*(t-{t0})*1.4))'"
                       f":enable='gte(t,{t0})':shortest=1[o{n}]")
        entrada = f"[o{n}]"
        n += 1
    final = pastas.final(ad["id"])
    if filtros:
        midia.run(ins + ["-filter_complex", ";".join(filtros) + f";{entrada}format=yuv420p[vf]", "-map", "[vf]", "-map", "0:a",
                         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "copy", "-movflags", "+faststart", final])
    else:
        midia.run(["-i", cat, "-c", "copy", "-movflags", "+faststart", final])

    if not midia.integro(final):
        raise midia.ErroMidia(f"{final} saiu corrompido")
    dur = midia.duracao(final)
    aviso = f" ⚠️ {dur:.0f}s < mínimo {op.min_dur:.0f}s" if dur < op.min_dur else ""
    log(f"  ✓ {ad['id']}: {dur:.1f}s, {len(segmentos)} segmentos, {len(eventos)} textos na tela{aviso}")
    return final
