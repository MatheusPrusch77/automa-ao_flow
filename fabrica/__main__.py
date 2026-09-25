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


def cmd_gerar_leva(a):
    from .gerador_leva import gerar_em_disco
    so = set(a.so.split(",")) if a.so else None
    destino, n = gerar_em_disco(a.modelo, a.avatares, a.pasta, a.por_avatar, a.semente, so)
    print(f"✓ {n} vídeos em {destino}")
    _, rel = L.carregar(destino)
    print(rel.texto())
    print(f"próximo: python -m fabrica pacote-flow {a.pasta}")


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


def _gerador(a, estado=None):
    """Uma leva nasce e termina no mesmo gerador: misturar clipes simulados com clipes reais
    (ou reaproveitar a pasta de um ensaio) monta vídeo com bipe no lugar da fala."""
    from .geradores import obter
    if estado is not None:
        anterior = estado.dados.get("gerador")
        if anterior and anterior != a.gerador:
            sys.exit(f"❌ esta leva foi gerada com o gerador '{anterior}', não '{a.gerador}'. "
                     f"Use uma pasta nova (ex.: levas\\2026-09-26) em vez de reaproveitar a do ensaio.")
        algo_pronto = any(os.listdir(d) for d in (Pastas(a.pasta).masters, Pastas(a.pasta).frames, Pastas(a.pasta).clips) if os.path.isdir(d))
        if not anterior and algo_pronto and a.gerador != "simulado":
            sys.exit("❌ esta pasta já tem imagens/clipes de antes, sem registro de qual gerador fez. "
                     "Use uma pasta nova para produzir de verdade.")
        estado.dados["gerador"] = a.gerador
        estado.salvar()
    return obter(a.gerador)


def cmd_masters(a):
    from .producao import fase_masters
    leva, pastas, estado = _carregar(a.pasta)
    fase_masters(leva, pastas, estado, _gerador(a, estado), forcar=a.refazer)
    print(f"🚦 grade: {qa.grade_masters(leva, pastas)}")


def cmd_frames(a):
    from .producao import fase_frames
    leva, pastas, estado = _carregar(a.pasta)
    _exige_aprovacao(estado, "masters", a)
    fase_frames(leva, pastas, estado, _gerador(a, estado), so=_so(a))
    print(f"🚦 grade: {qa.grade_frames(leva, pastas, _so(a))}")


def cmd_videos(a):
    from .producao import fase_videos, listar_falhas, resumo
    leva, pastas, estado = _carregar(a.pasta)
    _exige_aprovacao(estado, "frames", a)
    fase_videos(leva, pastas, estado, _gerador(a, estado), so=_so(a), max_simultaneos=a.max, intervalo_poll=a.poll,
                esperar=not a.sem_esperar)
    print(resumo(leva, estado))
    for f in listar_falhas(leva, estado):
        print("  ✗", f)


def cmd_produzir(a):
    """Tudo de uma vez: (gera a leva, se faltar) → masters → frames → vídeos → QA → montagem → ritmo."""
    from .montagem import Opcoes, montar_ad
    from .producao import fase_frames, fase_masters, fase_videos, listar_falhas, resumo
    pastas = Pastas(a.pasta)
    if not os.path.exists(pastas.leva_json):
        from .gerador_leva import gerar_em_disco
        so_av = set(a.avatares_so.split(",")) if a.avatares_so else None
        destino, n = gerar_em_disco(a.modelo, a.avatares, a.pasta, a.por_avatar, None, so_av)
        print(f"✓ leva gerada: {n} vídeos em {destino}")
    leva, pastas, estado = _carregar(a.pasta)
    so = _so(a)
    n_clipes = sum(len(ad["cenas"]) for ad in leva["ads"] if not so or ad["id"] in so)
    print(f"▶ {len(leva['ads'])} vídeos · {n_clipes} clipes de 8s (~{n_clipes * 8}s de vídeo gerado) · gerador {a.gerador}")
    g = _gerador(a, estado)
    print("1/5 masters (fotos dos avatares)")
    fase_masters(leva, pastas, estado, g)
    print("2/5 frames de cada cena")
    fase_frames(leva, pastas, estado, g, so=so)
    print(f"   grade para conferir: {qa.grade_frames(leva, pastas, so)}")
    if a.parar_nos_frames:
        print("⏸ parei nos frames (--parar-nos-frames). Confira a grade e rode de novo sem a flag.")
        return
    print("3/5 vídeos")
    fase_videos(leva, pastas, estado, g, so=so, max_simultaneos=a.max, intervalo_poll=a.poll)
    print("   ", resumo(leva, estado))
    for f in listar_falhas(leva, estado):
        print("   ✗", f)
    print("4/5 QA dos clipes")
    res = qa.gate_clipes(leva, pastas, so)
    for k, v in res.items():
        if not v.get("aprovado"):
            print(f"   ⚠️ {k}: {'; '.join(v.get('problemas', []))}")
    print("5/5 montagem")
    op = Opcoes.da_leva(leva.get("montagem"))
    prontos = 0
    for i, ad in enumerate(leva["ads"]):
        if so and ad["id"] not in so:
            continue
        try:
            final = montar_ad(ad, pastas, leva["idioma"], op, indice=i)
            r = ritmo.medir(final)
            prontos += 1
            if not r["aprovado"]:
                print(f"   ⚠️ ritmo {ad['id']}: {'; '.join(r['problemas'])}")
        except Exception as e:
            print(f"   ✗ {ad['id']}: {e}")
    print(f"✅ {prontos} vídeos prontos em {pastas.finais}")


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
    op = Opcoes.da_leva(leva.get("montagem"))  # o que a leva/modelo define; as flags só desligam
    op.punch_in &= not a.sem_punch
    op.legenda &= not a.sem_legenda
    op.headline &= not a.sem_headline
    op.cta &= not a.sem_cta
    op.aparar &= not a.sem_aparar
    op.crop_wm |= a.crop_wm
    if a.min_dur is not None:
        op.min_dur = a.min_dur
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
    p = novo("gerar-leva", cmd_gerar_leva, "monta o leva.json do dia a partir de um modelo e dos seus avatares")
    p.add_argument("pasta", help="pasta da leva do dia, ex.: levas/2026-09-26")
    p.add_argument("--modelo", default=os.path.join(os.path.dirname(AQUI), "modelos", "soda.json"))
    p.add_argument("--avatares", default=os.path.join(os.path.dirname(AQUI), "exemplos", "avatares.json"))
    p.add_argument("--por-avatar", type=int, default=3)
    p.add_argument("--so", help="só estes avatares: Alice,Frank")
    p.add_argument("--semente", type=int, help="fixa o sorteio (repetível)")
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
    p = novo("produzir", cmd_produzir, "faz tudo: gera a leva (se faltar), imagens, vídeos, QA e montagem")
    p.add_argument("pasta", help="pasta da leva do dia, ex.: levas/2026-09-26")
    p.add_argument("--gerador", default="veo", help="veo | simulado")
    p.add_argument("--modelo", default=os.path.join(os.path.dirname(AQUI), "modelos", "soda.json"))
    p.add_argument("--avatares", default=os.path.join(os.path.dirname(AQUI), "exemplos", "avatares.json"))
    p.add_argument("--avatares-so", help="só estes avatares ao gerar a leva: Alice,Frank")
    p.add_argument("--por-avatar", type=int, default=3)
    p.add_argument("--so", help="só estes vídeos: alice-1,frank-2")
    p.add_argument("--max", type=int, default=4, help="vídeos gerando ao mesmo tempo")
    p.add_argument("--poll", type=float, default=20.0)
    p.add_argument("--parar-nos-frames", action="store_true", help="para depois das imagens, antes de gastar com vídeo")
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
    p.add_argument("--min-dur", type=float, default=None, help="default: o da leva, ou 60")
    p = novo("ritmo", cmd_ritmo, "mede o ritmo (trocas/min, maior plano parado, silêncio)")
    p.add_argument("alvo", help="arquivo .mp4 ou pasta"); p.add_argument("--modo", choices=["criativo", "vsl"], default="criativo")
    p = novo("status", cmd_status, "resumo do estado da leva")
    p.add_argument("pasta")

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
