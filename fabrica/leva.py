"""Leitura e validação da leva (leva.json → estrutura normalizada com os prompts prontos).

Formato do leva.json: veja exemplos/leva-exemplo.json e docs/FORMATO-LEVA.md.

Validação em dois níveis (mesma filosofia do gerar_specs.py do pacote):
  ERRO  → a leva não roda (placeholder, travessão, fala fora de 15-26 palavras, persona inexistente…)
  AVISO → a leva roda, mas vai sair parada/fraca (3 tipos iguais seguidos, mecânica dominando, pouco choque…)
"""
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field

from . import prompts as P

CHOQUE = ("brain", "mannequin", "tower", "giant", "huge", "skull", "dozens", "hundred", "pile", "stack", "bucket",
          "crate", "hourglass", "pyramid", "cage", "enormous", "spill", "overflow", "flood", "knock", "scatter",
          "wall of", "covered in", "packed with", "oversized", "thousand", "smash", "pour over", "drips over",
          "inside a", "tumbling", "twice the width", "lying on the floor")

FALA_MIN, FALA_MAX, FALA_ALVO = 15, 26, (18, 24)
PROMPT_MAX = 600
ROUPA = r"\b(blouse|shirt|dress|sweater|cardigan|jacket|coat|top|t-shirt|tank|linen|silk|suit|hoodie|polo|scrubs|apron|uniform|vest)\b"


@dataclass
class Relatorio:
    erros: list = field(default_factory=list)
    avisos: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.erros

    def texto(self):
        linhas = [f"❌ {e}" for e in self.erros] + [f"⚠️  {a}" for a in self.avisos]
        return "\n".join(linhas) if linhas else "✅ leva sem erros nem avisos"


def palavras(s):
    return len(re.findall(r"\w+", s or "", re.U))


def fmt_n(n):
    n = float(n)
    return str(int(n)) if n.is_integer() else str(n)


def chave(ad_id, n):
    return f"{ad_id}_{fmt_n(n)}"


def _placeholder(txt):
    return bool(re.search(r"\{\{[^}]*\}\}|\{[A-Z_][A-Z0-9_]*\}", txt or ""))


def _checa_fala(onde, fala, rel):
    if not fala:
        return
    if _placeholder(fala):
        rel.erros.append(f"{onde}: placeholder não substituído na fala")
    if re.search(r"[—–]", fala):
        rel.erros.append(f"{onde}: travessão na fala vira sílaba fantasma — use vírgula ou ponto")
    if "..." in fala or "…" in fala:
        rel.erros.append(f"{onde}: reticências na fala fazem o gerador improvisar/embolar — use vírgula ou ponto")
    n = palavras(fala)
    if n < FALA_MIN:
        rel.erros.append(f"{onde}: fala com {n} palavras (<{FALA_MIN}) — o gerador inventa fala no tempo vazio; junte com a cena vizinha")
    elif n > FALA_MAX:
        rel.erros.append(f"{onde}: fala com {n} palavras (>{FALA_MAX}) — não cabe em 8s; divida em fim de frase")
    elif n < FALA_ALVO[0]:
        rel.avisos.append(f"{onde}: fala com {n} palavras, abaixo do alvo {FALA_ALVO[0]}-{FALA_ALVO[1]}")
    caps = re.search(r"\b[A-ZÀ-Ú]{3,}\b", fala)
    if caps:
        rel.avisos.append(f"{onde}: CAIXA ALTA na fala ('{caps.group(0)}') — o gerador tende a soletrar")


def _checa_prompt_en(onde, txt, rel):
    if re.search(r"[ãõçáéíóúâêôà]", txt or "", re.I):
        rel.avisos.append(f"{onde}: acento de português dentro do prompt visual — o prompt visual deve ser 100% inglês")
    if _placeholder(txt):
        rel.erros.append(f"{onde}: placeholder não substituído")


def carregar(caminho):
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    return normalizar(dados, base=os.path.dirname(os.path.abspath(caminho)))


def normalizar(dados, base="."):
    """Devolve (leva_normalizada, relatorio). A leva normalizada tem os prompts prontos por cena."""
    rel = Relatorio()
    idioma = dados.get("idioma", "pt")
    curto = dados.get("formato") == "curto"  # 15-30s, 1 avatar com vários vídeos no dia: relaxa as regras de corpo longo
    personas = dados.get("personas") or {}
    if not personas:
        rel.erros.append("leva sem 'personas'")

    for k, p in personas.items():
        if not p.get("descricao_visual") and not p.get("master_arquivo"):
            rel.erros.append(f"persona {k}: precisa de 'descricao_visual' ou de 'master_arquivo' (imagem que você criou no Flow)")
        if p.get("master_arquivo"):
            caminho = os.path.join(base, os.path.expanduser(p["master_arquivo"]))
            if not os.path.isfile(caminho):
                rel.erros.append(f"persona {k}: master_arquivo não encontrado: {p['master_arquivo']}")
            p["_master_path"] = caminho
        if p.get("descricao_visual"):
            _checa_prompt_en(f"persona {k}.descricao_visual", p["descricao_visual"], rel)
            if not re.search(ROUPA, p["descricao_visual"], re.I):
                rel.avisos.append(f"persona {k}: descricao_visual sem ROUPA explícita — sem isso todos os ads saem com a mesma camisa")
            if not p.get("cenario"):
                rel.avisos.append(f"persona {k}: sem 'cenario' — o master precisa de cenário + luz explícitos")
        if not p.get("voz"):
            rel.erros.append(f"persona {k}: sem 'voz' (sexo + idade + timbre + ritmo) — sem ela a voz muda entre clipes")
        elif not re.search(r"\b(woman|man|male|female)\b|\d", p["voz"]):
            rel.avisos.append(f"persona {k}: 'voz' sem sexo+idade explícitos — comece com 'woman/man around <idade>, …'")

    ads, ids = [], set()
    mecs, sem_choque, persona_por_ad = [], [], {}
    for i, item in enumerate(dados.get("itens") or []):
        ad = item.get("id") or f"AD-{i + 1:02d}"
        if ad in ids:
            rel.erros.append(f"id repetido: {ad}")
        ids.add(ad)
        cenas = []
        g = item.get("gancho")
        mec = ""
        if g:
            mec = (g.get("mecanica") or "").upper()
            gp = g.get("persona")
            if mec not in P.MECANICAS:
                rel.erros.append(f"{ad}.gancho.mecanica '{mec}' inválida — use {', '.join(P.MECANICAS)}")
            if gp not in personas:
                rel.erros.append(f"{ad}.gancho: persona '{gp}' não existe")
            av = (g.get("acao_visual") or "").strip()
            iv = (g.get("insert_visual") or "").strip()
            if not av:
                rel.erros.append(f"{ad}.gancho sem acao_visual")
            if mec in ("SPLIT", "INSERT_PRIMEIRO") and not iv:
                rel.erros.append(f"{ad}.gancho: {mec} exige insert_visual")
            if re.match(r"^\s*(the|a|an)\s+\d+[- ]year[- ]old", av, re.I):
                rel.avisos.append(f"{ad}.gancho abre redescrevendo a pessoa — abra na AÇÃO ('She pours…'); a referência já sabe quem é")
            if re.search(r"split screen|TOP:|BOTTOM:", av, re.I):
                rel.avisos.append(f"{ad}.gancho tem instrução de montagem (split/TOP/BOTTOM) — isso é da edição, não do gerador")
            if not any(c in f"{av} {iv}".lower() for c in CHOQUE):
                sem_choque.append(ad)
            _checa_fala(f"{ad}.gancho_fala", g.get("gancho_fala", ""), rel)
            if not g.get("gancho_fala"):
                rel.erros.append(f"{ad}.gancho sem gancho_fala — fala no segundo zero é lei")
            mecs.append(mec)
            if mec in ("SPLIT", "INSERT_PRIMEIRO"):
                cenas.append({"n": 0, "tipo": "I", "persona": gp, "acao": iv, "fala": "", "insert_gancho": True})
            acao_g = av + (" Medium shot, face fully in the upper half of the frame." if mec == "SPLIT" else "")
            cenas.append({"n": 1, "tipo": "G", "persona": gp, "acao": acao_g, "fala": g.get("gancho_fala", ""), "gancho": True})
        else:
            rel.avisos.append(f"{ad}: sem bloco 'gancho' — sem gancho separado a abertura vira pessoa parada falando")

        ns = {c["n"] for c in cenas}
        for c in item.get("cenas") or []:
            n = c.get("n")
            onde = f"{ad} cena {n}"
            if n is None:
                rel.erros.append(f"{ad}: cena sem 'n'")
                continue
            if n in ns:
                rel.erros.append(f"{onde}: n repetido (com gancho, o corpo começa em n=2)")
            ns.add(n)
            if c.get("persona") and c["persona"] not in personas:
                rel.erros.append(f"{onde}: persona '{c['persona']}' não existe")
            tipo = c.get("tipo") or ""
            if tipo and tipo not in P.TIPOS:
                rel.erros.append(f"{onde}: tipo '{tipo}' inválido — use {', '.join(P.TIPOS)}")
            if not c.get("acao"):
                rel.erros.append(f"{onde}: sem 'acao' (descrição visual em inglês)")
            _checa_prompt_en(f"{onde}.acao", c.get("acao", ""), rel)
            _checa_fala(onde, c.get("fala", ""), rel)
            cenas.append(dict(c))

        cenas.sort(key=lambda c: float(c["n"]))
        for c in cenas:
            p = personas.get(c.get("persona"), {})
            c["chave"] = chave(ad, c["n"])
            c["prompt_frame"] = P.prompt_frame(c, p)
            c["prompt_video"] = P.prompt_video(c, p, idioma)
            c["usa_master"] = c.get("tipo") != "I" and bool(c.get("persona"))
            if len(c["acao"]) > PROMPT_MAX:
                rel.avisos.append(f"{ad} cena {fmt_n(c['n'])}: acao com {len(c['acao'])} chars (>{PROMPT_MAX}) — prompt longo dispara recusa")

        corpo = [c.get("tipo") or "" for c in cenas if float(c["n"]) >= 2]
        if corpo:
            if not all(corpo):
                rel.avisos.append(f"{ad}: cena(s) do corpo sem 'tipo' — declare T-close/T-aberto/T-3/4/T-cta/D/I/L")
            for j in range(2, len(corpo)):
                if corpo[j] and corpo[j] == corpo[j - 1] == corpo[j - 2]:
                    rel.avisos.append(f"{ad}: 3 cenas seguidas do tipo {corpo[j]} — nunca 3 quadros iguais seguidos")
                    break
            bases = {t.split("-")[0] for t in corpo if t}
            if not curto and "I" not in bases:
                rel.avisos.append(f"{ad}: nenhum insert (I) no corpo — device/mecanismo/prova sem rosto")
            if not curto and "D" not in bases:
                rel.avisos.append(f"{ad}: nenhuma demonstração (D) no corpo")

        pks = tuple(sorted({c["persona"] for c in cenas if c.get("persona")}))
        if pks and pks in persona_por_ad and not curto:
            rel.avisos.append(f"{ad}: mesma persona de {persona_por_ad[pks]} — cada ad deve ter rosto/cenário próprios")
        persona_por_ad.setdefault(pks, ad)

        ads.append({"id": ad, "headline": item.get("headline", ""), "header_estilo": item.get("header_estilo", ""),
                    "cta": item.get("cta", dados.get("cta", "TOQUE E ASSISTA")), "mecanica": mec, "cenas": cenas})

    if not ads:
        rel.erros.append("leva sem 'itens'")
    if len(mecs) >= 4:
        dom, qtd = Counter(mecs).most_common(1)[0]
        if qtd / len(mecs) > 0.4:
            rel.avisos.append(f"LEVA: mecânica {dom} em {qtd}/{len(mecs)} ganchos — distribua SPLIT/INSERT_PRIMEIRO/ACAO/ESTRANHO")
    if mecs and len(sem_choque) / len(mecs) > 0.2:
        rel.avisos.append(f"LEVA: {len(sem_choque)}/{len(mecs)} ganchos sem elemento de choque detectado ({', '.join(sem_choque[:6])}) "
                          f"— confira à mão (o detector é por palavra)")

    leva = {"idioma": idioma, "personas": personas, "ads": ads, "cta": dados.get("cta", "TOQUE E ASSISTA"),
            "formato": dados.get("formato", "longo"), "montagem": dados.get("montagem", {})}
    return leva, rel


def tabela_prova(leva):
    """A tabela que o dono aprova antes de gerar (doc 08 §6), em markdown."""
    linhas = ["| id | persona | gancho | corpo (tipos) | headline |", "|---|---|---|---|---|"]
    for ad in leva["ads"]:
        g = next((c for c in ad["cenas"] if c.get("gancho")), None)
        pk = g["persona"] if g else next((c.get("persona") for c in ad["cenas"] if c.get("persona")), "")
        corpo = "·".join(c.get("tipo") or "?" for c in ad["cenas"] if float(c["n"]) >= 2)
        gtxt = f"{ad['mecanica']}: {g['acao'][:70]}…" if g else "—"
        linhas.append(f"| {ad['id']} | {pk} | {gtxt} | {corpo} | {ad['headline']} |")
    return "\n".join(linhas)
