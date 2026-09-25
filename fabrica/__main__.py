"""CLI da fábrica de criativos.  Uso: python -m fabrica <comando> <pasta-da-leva> [opções]

Fluxo típico (API do Veo):
  nova → validar → masters → aprovar masters → frames → aprovar frames → videos → qa → montar → ritmo
Fluxo típico (Flow manual):
  nova → validar → pacote-flow → (gera no Flow) → ingerir --tipo clipes → qa → montar → ritmo
"""
import argparse
import json
import os
import shutil
import sys

from . import leva as L
from . import qa, ritmo
from .estado import Estado, Pastas

AQUI = os.path.dirname(os.path.abspath(__file__))
EXEMPLO = os.path.join(os.path.dirname(AQUI), "exemplos", "leva-exemplo.json")


def _carregar(pasta, exigir_ok=True):
    pastas = Pastas(pasta).criar()
    if not os.path.exists(pastas.leva_json):
        sys.exit(f"não achei {pastas.leva_json} — crie com: python -m fabrica nova {pasta}")
    leva, rel = L.carregar(pastas.leva_json)
    if exigir_ok and not rel.ok:
        print(rel.texto())
        sys.exit("❌ corrija os erros da leva antes de seguir (python -m fabrica validar …)")
    return leva, pastas, Estado(pastas.estado)


def _so(args):
    return set(args.so.split(",")) if getattr(args, "so", None) else None


def _exige_aprovacao(estado, etapa, args):
    if args.forcar or estado.dados.get("aprovacoes", {}).get(etapa):
        return
    sys.exit(f"🚦 gate: olhe qa/GRADE-{etapa.upper()}.jpg e rode `python -m fabrica aprovar {args.pasta} {etapa}` "
             f"(ou use --forcar). Gerar vídeo em cima de {etapa} ruim é o desperdício mais caro da leva.")


def cmd_nova(a):
    pastas = Pastas(a.pasta).criar()
    if os.path.exists(pastas.leva_json):
        sys.exit(f"{pastas.leva_json} já existe")
    shutil.copyfile(a.de or EXEMPLO, pastas.leva_json)
    print(f"✓ leva criada em {pastas.raiz} — edite leva.json e rode `python -m fabrica validar {a.pasta}`")


def cmd_validar(a):
    leva, pastas, _ = _carregar(a.pasta, exigir_ok=False)
    _, rel = L.carregar(pastas.leva_json)
    print(rel.texto())
    tabela = L.tabela_prova(leva)
    with open(os.path.join(pastas.qa, "TABELA-PROVA.md"), "w", encoding="utf-8") as f:
        f.write(tabela + "\n")
    print("\n" + tabela)
    n = sum(len(ad["cenas"]) for ad in leva["ads"])
    print(f"\n{len(leva['ads'])} ads · {n} clipes de ~8s · tabela-prova em qa/TABELA-PROVA.md")
    if a.prompts:
        for ad in leva["ads"]:
            for c in ad["cenas"]:
                print(f"\n── {c['chave']} [{len(c['prompt_frame'])} / {len(c['prompt_video'])} chars]\nFRAME: {c['prompt_frame']}\nVIDEO: {c['prompt_video']}")
    sys.exit(0 if rel.ok else 1)


def _gerador(a):
    from .geradores import obter
    return obter(a.gerador)


def cmd_masters(a):
    from .producao import fase_masters
    leva, pastas, estado = _carregar(a.pasta)
    fase_masters(leva, pastas, estado, _gerador(a), forcar=a.refazer)
    print(f"🚦 grade: {qa.grade_masters(leva, pastas)}")


def cmd_frames(a):
    from .producao import fase_frames
    leva, pastas, estado = _carregar(a.pasta)
    _exige_aprovacao(estado, "masters", a)
    fase_frames(leva, pastas, estado, _gerador(a), so=_so(a))
    print(f"🚦 grade: {qa.grade_frames(leva, pastas, _so(a))}")


def cmd_videos(a):
    from .producao import fase_videos, listar_falhas, resumo
    leva, pastas, estado = _carregar(a.pasta)
    _exige_aprovacao(estado, "frames", a)
    fase_videos(leva, pastas, estado, _gerador(a), so=_so(a), max_simultaneos=a.max, intervalo_poll=a.poll,
                esperar=not a.sem_esperar)
    print(resumo(leva, estado))
    for f in listar_falhas(leva, estado):
        print("  ✗", f)


def cmd_aprovar(a):
    _, pastas, estado = _carregar(a.pasta, exigir_ok=False)
    estado.dados.setdefault("aprovacoes", {})[a.etapa] = True
    estado.salvar()
    print(f"✓ {a.etapa} aprovado")


def cmd_refazer(a):
    """Apaga frame/clipe de cenas específicas para regerar só elas (o master fica)."""
    leva, pastas, estado = _carregar(a.pasta, exigir_ok=False)
    for chave in a.chaves:
        for p in ((pastas.frame(chave),) if a.frame else ()) + (pastas.clipe(chave),):
            if os.path.exists(p):
                os.remove(p)
        estado.dados["cenas"].pop(chave, None)
        print(f"  ↺ {chave}")
    estado.salvar()


def cmd_pacote(a):
    from .flow_manual import exportar_pacote
    leva, pastas, _ = _carregar(a.pasta)
    print(f"✓ pacote: {exportar_pacote(leva, pastas)}")


def cmd_ingerir(a):
    from .flow_manual import ingerir
    leva, pastas, _ = _carregar(a.pasta)
    plano, aplicado = ingerir(leva, pastas, os.path.expanduser(a.de), a.tipo, a.por_ordem, a.confirmar, a.mover)
    for src, chave, _ in plano:
        print(f"  {'✓' if aplicado else '?'} {os.path.basename(src)} → {chave}")
    if not plano:
        print("nada a ingerir (nomes não batem? use --por-ordem)")
    elif not aplicado:
        print("mapeamento POR ORDEM de download — confira acima e repita com --confirmar")


def cmd_qa(a):
    leva, pastas, _ = _carregar(a.pasta)
    res = qa.gate_clipes(leva, pastas, _so(a))
    ruins = {k: v for k, v in res.items() if not v.get("aprovado")}
    for k, v in ruins.items():
        print(f"  ✗ {k}: {'; '.join(v['problemas'])}")
    print(f"{len(res) - len(ruins)}/{len(res)} clipes aprovados · qa/GATE-CLIPES.json")
    from . import transcricao
    if not transcricao.disponivel():
        print("  (sem whisper: a camada de FALA não rodou — pip install faster-whisper)")


def cmd_montar(a):
    from .montagem import Opcoes, montar_ad
    leva, pastas, _ = _carregar(a.pasta)
    op = Opcoes(punch_in=not a.sem_punch, legenda=not a.sem_legenda, headline=not a.sem_headline, cta=not a.sem_cta,
                crop_wm=a.crop_wm, min_dur=a.min_dur, aparar=not a.sem_aparar)
    erros = 0
    for i, ad in enumerate(leva["ads"]):
        if _so(a) and ad["id"] not in _so(a):
            continue
        try:
            montar_ad(ad, pastas, leva["idioma"], op, indice=i)
        except Exception as e:
            erros += 1
            print(f"  ✗ {ad['id']}: {e}")
    sys.exit(1 if erros else 0)


def cmd_ritmo(a):
    alvos = [os.path.join(a.alvo, f) for f in sorted(os.listdir(a.alvo)) if f.endswith(".mp4")] if os.path.isdir(a.alvo) else [a.alvo]
    reprovou = False
    for p in alvos:
        r = ritmo.medir(p, a.modo)
        reprovou |= not r["aprovado"]
        print(f"{'🟢' if r['aprovado'] else '🔴'} {os.path.basename(p)}: {r['duracao']}s · {r['trocas_por_min']} trocas/min · "
              f"maior plano {r['maior_plano']}s{' · ' + '; '.join(r['problemas']) if r['problemas'] else ''}")
    sys.exit(1 if reprovou else 0)


def cmd_status(a):
    from .producao import listar_falhas, resumo
    leva, pastas, estado = _carregar(a.pasta, exigir_ok=False)
    print(json.dumps({"aprovacoes": estado.dados.get("aprovacoes", {}), "cenas": resumo(leva, estado),
                      "finais": sorted(os.listdir(pastas.finais))}, ensure_ascii=False, indent=1))
    for f in listar_falhas(leva, estado):
        print("  ✗", f)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m fabrica", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def novo(nome, fn, ajuda):
        p = sub.add_parser(nome, help=ajuda)
        p.set_defaults(fn=fn)
        return p

    p = novo("nova", cmd_nova, "cria a pasta da leva com um leva.json modelo")
    p.add_argument("pasta"); p.add_argument("--de", help="leva.json a copiar (default: exemplo)")
    p = novo("validar", cmd_validar, "valida a leva e gera a tabela-prova")
    p.add_argument("pasta"); p.add_argument("--prompts", action="store_true", help="imprime todos os prompts")
    for nome, fn, ajuda in (("masters", cmd_masters, "gera as imagens-mestre (rostos)"),
                            ("frames", cmd_frames, "gera o frame inicial de cada cena"),
                            ("videos", cmd_videos, "gera os clipes (image-to-video)")):
        p = novo(nome, fn, ajuda)
        p.add_argument("pasta"); p.add_argument("--gerador", default="veo", help="veo | simulado")
        p.add_argument("--so", help="só estes ads: AD-01,AD-02"); p.add_argument("--forcar", action="store_true")
        if nome == "masters":
            p.add_argument("--refazer", action="store_true")
        if nome == "videos":
            p.add_argument("--max", type=int, default=4, help="operações simultâneas")
            p.add_argument("--poll", type=float, default=20.0, help="segundos entre polls")
            p.add_argument("--sem-esperar", action="store_true", help="envia e sai; rode de novo depois pra baixar")
    p = novo("aprovar", cmd_aprovar, "marca um gate como aprovado (masters | frames)")
    p.add_argument("pasta"); p.add_argument("etapa", choices=["masters", "frames"])
    p = novo("refazer", cmd_refazer, "apaga clipe (e opcionalmente frame) de cenas para regerar")
    p.add_argument("pasta"); p.add_argument("chaves", nargs="+", help="ex.: AD-01_1 AD-03_4"); p.add_argument("--frame", action="store_true")
    p = novo("pacote-flow", cmd_pacote, "gera o pacote HTML de prompts para produzir no Flow à mão")
    p.add_argument("pasta")
    p = novo("ingerir", cmd_ingerir, "puxa imagens/clipes baixados do Flow para a leva")
    p.add_argument("pasta"); p.add_argument("--de", default="~/Downloads"); p.add_argument("--tipo", choices=["masters", "frames", "clipes"], default="clipes")
    p.add_argument("--por-ordem", action="store_true"); p.add_argument("--confirmar", action="store_true"); p.add_argument("--mover", action="store_true")
    p = novo("qa", cmd_qa, "gate dos clipes (integridade, frame, fala)")
    p.add_argument("pasta"); p.add_argument("--so")
    p = novo("montar", cmd_montar, "monta os finais 1080x1920")
    p.add_argument("pasta"); p.add_argument("--so")
    for f in ("--sem-punch", "--sem-legenda", "--sem-headline", "--sem-cta", "--sem-aparar", "--crop-wm"):
        p.add_argument(f, action="store_true")
    p.add_argument("--min-dur", type=float, default=60.0)
    p = novo("ritmo", cmd_ritmo, "mede o ritmo (trocas/min, maior plano parado, silêncio)")
    p.add_argument("alvo", help="arquivo .mp4 ou pasta"); p.add_argument("--modo", choices=["criativo", "vsl"], default="criativo")
    p = novo("status", cmd_status, "resumo do estado da leva")
    p.add_argument("pasta")

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
