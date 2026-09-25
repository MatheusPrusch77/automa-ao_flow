"""Gera o leva.json do dia a partir de um MODELO (modelos/*.json) e da lista de AVATARES.

Cada vídeo = 4 cenas: gancho → preparo → explicação → CTA. As falas vêm de uma VERSÃO do
modelo (+ o CTA fixo); o visual combina gancho, preparo, explicação e CTA. No mesmo dia,
cada avatar recebe versões e ganchos diferentes; entre dias, nenhuma combinação se repete
para o mesmo avatar (histórico em disco).
"""
import json
import os
import random
import re

PRONOMES = {"f": ("She", "she", "her"), "m": ("He", "he", "his")}


def slug(nome):
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


def _troca(txt, sexo):
    S, s, pos = PRONOMES.get(sexo, PRONOMES["f"])
    return txt.replace("{S}", S).replace("{s}", s).replace("{pos}", pos)


def combinacoes(modelo):
    """Todas as combinações (índices): versão, gancho, preparo, explicação, cta visual."""
    return [(v, g, p, e, c) for v in range(len(modelo["versoes"])) for g in range(len(modelo["ganchos"]))
            for p in range(len(modelo["preparos"])) for e in range(len(modelo["explicacoes"]))
            for c in range(len(modelo["ctas_visuais"]))]


def _escolher(livres, por_avatar, modelo, uso_mecanica):
    """Até por_avatar combinações com versão e gancho diferentes (relaxa a versão se faltar)."""
    for exigir_versao in (True, False):
        escolhidas, versoes, ganchos = [], set(), set()
        for c in livres:
            if c[1] in ganchos or (exigir_versao and c[0] in versoes):
                continue
            escolhidas.append(c)
            versoes.add(c[0])
            ganchos.add(c[1])
            if len(escolhidas) == por_avatar:
                break
        if len(escolhidas) == por_avatar or not exigir_versao:
            break
    for c in escolhidas:
        mec = modelo["ganchos"][c[1]]["mecanica"]
        uso_mecanica[mec] = uso_mecanica.get(mec, 0) + 1
    return escolhidas


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
        livres.sort(key=lambda c: uso_mecanica.get(modelo["ganchos"][c[1]]["mecanica"], 0))  # sort estável: mantém o sorteio
        for k, (v, g, p, e, c) in enumerate(_escolher(livres, por_avatar, modelo, uso_mecanica), 1):
            versao = modelo["versoes"][v]
            f1, f2, f3 = versao["falas"]
            gancho = modelo["ganchos"][g]
            bloco = {"mecanica": gancho["mecanica"], "persona": pk,
                     "acao_visual": _troca(gancho["acao_visual"], sexo), "gancho_fala": f1}
            if gancho.get("insert_visual"):
                bloco["insert_visual"] = _troca(gancho["insert_visual"], sexo)
            expl = modelo["explicacoes"][e]
            itens.append({
                "id": f"{pk}-{k}",
                "_combinacao": {"versao": versao["nome"], "gancho": g, "preparo": p, "explicacao": e, "cta": c},
                "gancho": bloco,
                "cenas": [
                    {"n": 2, "tipo": "D", "persona": pk, "acao": _troca(modelo["preparos"][p], sexo), "fala": f2},
                    {"n": 3, "tipo": expl["tipo"], "persona": pk, "acao": _troca(expl["acao"], sexo), "fala": f3},
                    {"n": 4, "tipo": "T-cta", "persona": pk, "acao": _troca(modelo["ctas_visuais"][c], sexo),
                     "fala": modelo["cta_fala"]},
                ],
            })
            novos.setdefault(pk, []).append([v, g, p, e, c])
    leva = {"idioma": modelo.get("idioma", "en"), "formato": modelo.get("formato", "curto"),
            "fala_min": modelo.get("fala_min", 15), "montagem": modelo.get("montagem", {}),
            "personas": personas, "itens": itens}
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
