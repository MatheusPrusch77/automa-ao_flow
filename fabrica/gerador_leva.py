"""Gera o leva.json do dia a partir de um MODELO (modelos/*.json) e da lista de AVATARES.

Cada vídeo = gancho (abertura) → preparo (meio) → CTA, uma peça de cada lista do modelo.
Não repete a mesma combinação para o mesmo avatar (histórico em disco) e, dentro do dia,
cada avatar recebe ganchos e aberturas diferentes nos seus vídeos.
"""
import json
import os
import random
import re

PRONOMES = {"f": ("She", "she", "her"), "m": ("He", "he", "his")}


def slug(nome):
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


def _troca(txt, sexo, parte=""):
    S, s, pos = PRONOMES.get(sexo, PRONOMES["f"])
    return txt.replace("{S}", S).replace("{s}", s).replace("{pos}", pos).replace("{parte}", parte)


def combinacoes(modelo):
    """Todas as combinações possíveis (índices), na ordem: abertura, parte, meio, cta, gancho."""
    return [(a, p, m, c, g) for a in range(len(modelo["aberturas"])) for p in range(len(modelo["partes"]))
            for m in range(len(modelo["meios"])) for c in range(len(modelo["ctas"])) for g in range(len(modelo["ganchos"]))]


def gerar(modelo, avatares, por_avatar=3, semente=None, historico=None, base_avatares="."):
    """Devolve (leva_dict, novas_entradas_de_historico)."""
    rnd = random.Random(semente)
    historico = historico or {}
    todas = combinacoes(modelo)
    personas, itens, novos = {}, [], {}
    uso_mecanica = {}  # equilibra SPLIT/INSERT_PRIMEIRO/ACAO/ESTRANHO na leva inteira
    for nome, av in avatares.items():
        if nome.startswith("_"):
            continue
        pk = slug(nome)
        sexo = av.get("sexo", "f")
        personas[pk] = {"master_arquivo": os.path.normpath(os.path.join(base_avatares, av["arquivo"])),
                        "voz": av["voz"], "cenario": av.get("cenario", "")}
        usadas = {tuple(x) for x in historico.get(pk, [])}
        livres = [c for c in todas if c not in usadas] or todas  # esgotou: recomeça o ciclo
        rnd.shuffle(livres)
        livres.sort(key=lambda c: uso_mecanica.get(modelo["ganchos"][c[4]]["mecanica"], 0))  # sort estável: mantém o sorteio
        escolhidas, ganchos_dia, aberturas_dia = [], set(), set()
        for c in livres:  # no mesmo dia, gancho e abertura diferentes em cada vídeo do avatar
            if c[4] in ganchos_dia or c[0] in aberturas_dia:
                continue
            escolhidas.append(c)
            mec = modelo["ganchos"][c[4]]["mecanica"]
            uso_mecanica[mec] = uso_mecanica.get(mec, 0) + 1
            ganchos_dia.add(c[4])
            aberturas_dia.add(c[0])
            if len(escolhidas) == por_avatar:
                break
        for k, (a, p, m, c, g) in enumerate(escolhidas, 1):
            parte = modelo["partes"][p]
            gancho = modelo["ganchos"][g]
            bloco = {"mecanica": gancho["mecanica"], "persona": pk,
                     "acao_visual": _troca(gancho["acao_visual"], sexo),
                     "gancho_fala": _troca(modelo["aberturas"][a], sexo, parte)}
            if gancho.get("insert_visual"):
                bloco["insert_visual"] = _troca(gancho["insert_visual"], sexo)
            itens.append({
                "id": f"{pk}-{k}",
                "_combinacao": {"abertura": a, "parte": parte, "meio": m, "cta": c, "gancho": g},
                "gancho": bloco,
                "cenas": [
                    {"n": 2, "tipo": "D", "persona": pk, "acao": _troca(rnd.choice(modelo["demos"]), sexo),
                     "fala": modelo["meios"][m]},
                    {"n": 3, "tipo": "T-cta", "persona": pk, "acao": _troca(rnd.choice(modelo["ctas_visuais"]), sexo),
                     "fala": modelo["ctas"][c]},
                ],
            })
            novos.setdefault(pk, []).append([a, p, m, c, g])
    leva = {"idioma": modelo.get("idioma", "en"), "formato": modelo.get("formato", "curto"),
            "montagem": modelo.get("montagem", {}), "personas": personas, "itens": itens}
    return leva, novos


def gerar_em_disco(caminho_modelo, caminho_avatares, pasta_leva, por_avatar=3, semente=None, so=None):
    with open(caminho_modelo, encoding="utf-8") as f:
        modelo = json.load(f)
    with open(caminho_avatares, encoding="utf-8") as f:
        avatares = json.load(f)
    if so:
        avatares = {k: v for k, v in avatares.items() if slug(k) in so or k in so}
    base_av = os.path.dirname(os.path.abspath(caminho_avatares))
    # histórico fica ao lado das levas (uma pasta acima da leva) e vale por modelo
    hist_path = os.path.join(os.path.dirname(os.path.abspath(pasta_leva)),
                             f"historico-{os.path.splitext(os.path.basename(caminho_modelo))[0]}.json")
    historico = {}
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8") as f:
            historico = json.load(f)
    leva, novos = gerar(modelo, avatares, por_avatar, semente, historico, base_av)
    os.makedirs(pasta_leva, exist_ok=True)
    destino = os.path.join(pasta_leva, "leva.json")
    if os.path.exists(destino):
        raise SystemExit(f"{destino} já existe — use outra pasta (uma por dia)")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(leva, f, ensure_ascii=False, indent=1)
    for pk, lst in novos.items():
        historico.setdefault(pk, []).extend(lst)
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(historico, f)
    return destino, len(leva["itens"])
