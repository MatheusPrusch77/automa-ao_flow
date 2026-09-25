"""Modo Flow manual-assistido: você gera no Flow (na sua conta, do jeito que o Flow foi feito
para ser usado) e a fábrica faz todo o resto.

  1. `pacote-flow`  → gera pacote-flow/index.html: para cada persona e cada cena, o prompt
     pronto com botão de copiar, a referência a usar e o NOME do arquivo a salvar.
  2. Você gera no Flow e baixa (pode deixar na pasta Downloads).
  3. `ingerir`      → puxa os arquivos para masters/, frames/ ou clips/ pelo nome (AD-01_3.mp4)
     ou pela ordem de download (--por-ordem), e o pipeline segue: QA → montagem → ritmo.
"""
import html
import os
import re
import shutil

from PIL import Image

from .prompts import prompt_master

EXT_VIDEO = (".mp4", ".mov", ".webm", ".m4v")
EXT_IMG = (".png", ".jpg", ".jpeg", ".webp")


def exportar_pacote(leva, pastas):
    os.makedirs(pastas.pacote, exist_ok=True)
    blocos = []
    usadas = sorted({c["persona"] for ad in leva["ads"] for c in ad["cenas"] if c.get("usa_master")})
    blocos.append("<h2>1 · Masters (imagem-mestre de cada persona)</h2>"
                  "<p class=dica>Gere no Flow em modo imagem, 9:16. Escolha o melhor rosto e salve com o nome indicado "
                  "(ou deixe em Downloads e use <code>ingerir --tipo masters</code>). Se a persona já tem uma imagem sua, pule.</p>")
    for pk in usadas:
        p = leva["personas"][pk]
        img = _thumb(pastas.master(pk), pastas)
        if p.get("_master_path"):
            blocos.append(_card(f"master {pk}", f"{pk}.png", "Já definido por master_arquivo — nada a gerar.", None, img))
        else:
            blocos.append(_card(f"master {pk}", f"{pk}.png", prompt_master(p), None, img))

    blocos.append("<h2>2 · Frames e vídeos, cena a cena</h2>"
                  "<p class=dica><b>Frame:</b> modo imagem, anexando o master da persona como referência (ingrediente). "
                  "Inserts (tipo I) vão sem referência de pessoa.<br><b>Vídeo:</b> modo Frames-para-vídeo com o frame aprovado "
                  "como quadro inicial, 9:16. Salve com o nome indicado.</p>")
    for ad in leva["ads"]:
        blocos.append(f"<h3>{html.escape(ad['id'])} · {html.escape(ad.get('mecanica') or 'sem gancho')} · "
                      f"{html.escape(ad.get('headline', ''))}</h3>")
        for c in ad["cenas"]:
            ref = "sem referência (insert)" if not c.get("usa_master") else f"master <b>{c['persona']}</b>"
            titulo = f"{c['chave']} · tipo {c.get('tipo') or '-'} · ref: {ref}"
            blocos.append(_card(titulo, f"{c['chave']}.png / {c['chave']}.mp4", c["prompt_frame"], c["prompt_video"],
                                _thumb(pastas.frame(c["chave"]), pastas), pronto=os.path.exists(pastas.clipe(c["chave"]))))
    caminho = os.path.join(pastas.pacote, "index.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(_HTML.replace("{{CORPO}}", "\n".join(blocos)))
    return caminho


def _thumb(path, pastas):
    if not os.path.exists(path):
        return None
    return os.path.relpath(path, pastas.pacote)


def _card(titulo, arquivo, p_img, p_vid, thumb, pronto=False):
    t = f"<img src='{html.escape(thumb)}'>" if thumb else ""
    vid = (f"<div class=lbl>Prompt do VÍDEO</div><pre>{html.escape(p_vid)}</pre><button onclick=cp(this)>copiar</button>"
           if p_vid else "")
    ok = " ok" if pronto else ""
    return (f"<div class='card{ok}'>{t}<div class=tit>{titulo}</div><div class=arq>salvar como: <code>{html.escape(arquivo)}</code></div>"
            f"<div class=lbl>Prompt da IMAGEM</div><pre>{html.escape(p_img)}</pre><button onclick=cp(this)>copiar</button>{vid}</div>")


_HTML = """<!doctype html><html lang=pt-BR><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Pacote Flow</title><style>
:root{--bg:#f6f6f4;--fg:#1d1d1b;--card:#fff;--mut:#6b6b66;--ok:#e7f6ea;--bd:#ddd}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#eee;--card:#222220;--mut:#9a9a94;--ok:#1d3322;--bd:#333}}
body{font:15px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:980px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px;margin:10px 0;overflow:hidden}
.card.ok{background:var(--ok)} .card img{float:right;width:110px;margin-left:12px;border-radius:6px}
.tit{font-weight:700}.arq,.dica{color:var(--mut)}.lbl{margin-top:8px;font-size:12px;text-transform:uppercase;color:var(--mut)}
pre{white-space:pre-wrap;word-break:break-word;background:rgba(127,127,127,.1);padding:8px;border-radius:6px;margin:4px 0}
button{cursor:pointer;border:1px solid var(--bd);background:var(--card);color:var(--fg);border-radius:6px;padding:4px 10px}
</style><h1>Pacote Flow</h1><p class=dica>Cards verdes = clipe já ingerido. Recarregue depois de rodar <code>ingerir</code>.</p>
{{CORPO}}
<script>function cp(b){navigator.clipboard.writeText(b.previousElementSibling.textContent);b.textContent='copiado ✓';setTimeout(()=>b.textContent='copiar',1200)}</script>
"""


def pendentes(leva, pastas, tipo):
    if tipo == "masters":
        usadas = sorted({c["persona"] for ad in leva["ads"] for c in ad["cenas"] if c.get("usa_master")})
        return [(pk, pastas.master(pk)) for pk in usadas if not os.path.exists(pastas.master(pk))]
    out = []
    for ad in leva["ads"]:
        for c in ad["cenas"]:
            destino = pastas.frame(c["chave"]) if tipo == "frames" else pastas.clipe(c["chave"])
            if not os.path.exists(destino):
                out.append((c["chave"], destino))
    return out


def ingerir(leva, pastas, origem, tipo, por_ordem=False, confirmar=False, mover=False):
    """Devolve a lista [(arquivo_origem, chave, destino)] do que foi (ou seria) ingerido."""
    exts = EXT_VIDEO if tipo == "clipes" else EXT_IMG
    arquivos = [os.path.join(origem, f) for f in os.listdir(origem) if f.lower().endswith(exts)]
    faltam = pendentes(leva, pastas, tipo)
    plano, usados = [], set()
    for chave_, destino in faltam:
        padrao = re.compile(rf"(^|[^0-9A-Za-z.]){re.escape(chave_)}([^0-9A-Za-z.]|\.[a-z0-9]+$)", re.I)
        achado = next((a for a in arquivos if a not in usados and padrao.search(os.path.basename(a))), None)
        if achado:
            plano.append((achado, chave_, destino))
            usados.add(achado)
    if por_ordem:
        restantes = sorted((a for a in arquivos if a not in usados), key=os.path.getmtime)
        sem_par = [(k, d) for k, d in faltam if k not in {p[1] for p in plano}]
        for a, (k, d) in zip(restantes, sem_par):
            plano.append((a, k, d))
        if not confirmar:
            return plano, False  # por ordem é arriscado: mostra o mapeamento e só aplica com --confirmar
    for a, _, d in plano:
        if tipo == "clipes":
            (shutil.move if mover else shutil.copyfile)(a, d)
        else:
            Image.open(a).convert("RGB").save(d)
            if mover:
                os.remove(a)
    return plano, True

