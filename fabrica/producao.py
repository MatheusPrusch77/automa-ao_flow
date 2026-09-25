"""As fases de geração, idempotentes e retomáveis pelo estado.json:

  masters → (gate: você olha a grade de rostos) → frames → (gate: grade das cenas) → videos

Ritmo calmo de propósito (pausa entre envios, poll folgado, limite de operações simultâneas):
volume em rajada é o que derruba conta e estoura cota."""
import os
import time

from .leva import fmt_n


def _log(msg):
    print(msg, flush=True)


def fase_masters(leva, pastas, estado, gerador, forcar=False):
    usadas = {c["persona"] for ad in leva["ads"] for c in ad["cenas"] if c.get("usa_master")}
    for pk in sorted(usadas):
        p = leva["personas"][pk]
        destino = pastas.master(pk)
        st = estado.master(pk)
        if os.path.exists(destino) and not forcar:
            continue
        if p.get("_master_path"):  # imagem que você já criou no Flow: vira o master sem gerar nada
            from PIL import Image
            im = Image.open(p["_master_path"]).convert("RGB")
            im.thumbnail((1080, 1920))  # foto de 3000x5000 só pesa no envio; 1080x1920 basta de referência
            im.save(destino)
            st.update(arquivo=destino, origem="arquivo")
            _log(f"  master {pk}: copiado de {p['master_arquivo']}")
        else:
            from .prompts import prompt_master
            _log(f"  master {pk}: gerando…")
            gerador.imagem(prompt_master(p), None, destino)
            st.update(arquivo=destino, origem="gerado")
        estado.salvar()


class ParadaSeguidas(SystemExit):
    pass


def _falhas_seguidas(contador, erro, limite=3):
    """Os primeiros pedidos falhando todos = problema de conta/chave/cota, não de conteúdo: para e mostra o motivo."""
    contador.append(erro)
    if len(contador) >= limite:
        raise ParadaSeguidas(
            f"\n❌ {limite} falhas seguidas logo no início — parei para não insistir à toa.\n   Motivo: {erro}\n"
            "   Causas comuns: faturamento não ativado no Google AI Studio, cota do plano gratuito (429/quota), "
            "chave inválida (401/403/API key).")


def fase_frames(leva, pastas, estado, gerador, so=None, pausa=1.0):
    falhas = []  # vira None ao primeiro sucesso: daí em diante falha é por cena, não de conta
    for ad in leva["ads"]:
        if so and ad["id"] not in so:
            continue
        for c in ad["cenas"]:
            destino = pastas.frame(c["chave"])
            if os.path.exists(destino):
                continue
            ref = None
            if c.get("usa_master"):
                ref = pastas.master(c["persona"])
                if not os.path.exists(ref):
                    # sem master = rosto aleatório em cada cena. Melhor pular do que produzir lixo.
                    _log(f"  PULADO {c['chave']}: sem master de '{c['persona']}' (rode a fase masters)")
                    continue
            _log(f"  frame {c['chave']} ({c.get('tipo') or '-'})")
            try:
                gerador.imagem(c["prompt_frame"], ref, destino)
                estado.cena(c["chave"]).update(frame=destino, status="frame_ok")
                falhas[:] = [None]
            except Exception as e:  # recusa de conteúdo, cota, rede: registra e segue a leva
                st = estado.cena(c["chave"])
                st.update(status="frame_falhou", erro=str(e)[:300])
                _log(f"    ✗ {e}")
                estado.salvar()
                if falhas != [None]:
                    _falhas_seguidas(falhas, str(e)[:400])
            estado.salvar()
            time.sleep(pausa)


def fase_videos(leva, pastas, estado, gerador, so=None, max_simultaneos=4, intervalo_poll=20.0,
                pausa_envio=2.0, max_tentativas=3, esperar=True):
    fila = []
    for ad in leva["ads"]:
        if so and ad["id"] not in so:
            continue
        for c in ad["cenas"]:
            if os.path.exists(pastas.clipe(c["chave"])):
                estado.cena(c["chave"]).update(status="pronto")
                continue
            fila.append(c)
    estado.salvar()
    em_voo = {k: v for k, v in estado.dados["cenas"].items() if v.get("status") == "enviado" and v.get("op")}
    falhas_envio = []  # vira [None] no primeiro envio aceito

    def enviar(c):
        st = estado.cena(c["chave"])
        frame = pastas.frame(c["chave"])
        if not os.path.exists(frame):
            _log(f"  PULADO {c['chave']}: sem frame aprovado (rode a fase frames)")
            return False
        try:
            op = gerador.enviar_video(c["prompt_video"], frame, pastas.clipe(c["chave"]))
            st.update(status="enviado", op=op, tentativas=st.get("tentativas", 0) + 1, erro="")
            em_voo[c["chave"]] = st
            falhas_envio[:] = [None]
            _log(f"  ▶ enviado {c['chave']} (tentativa {st['tentativas']})")
        except Exception as e:
            st.update(status="falhou", tentativas=st.get("tentativas", 0) + 1, erro=str(e)[:300])
            _log(f"  ✗ envio {c['chave']}: {e}")
            estado.salvar()
            if falhas_envio != [None] and not em_voo:
                _falhas_seguidas(falhas_envio, str(e)[:400])
        estado.salvar()
        time.sleep(pausa_envio)
        return True

    pendentes = [c for c in fila if c["chave"] not in em_voo]
    por_chave = {c["chave"]: c for c in fila}
    while pendentes or em_voo:
        while pendentes and len(em_voo) < max_simultaneos:
            c = pendentes.pop(0)
            st = estado.cena(c["chave"])
            if st.get("status") == "falhou" and st.get("tentativas", 0) >= max_tentativas:
                _log(f"  ⛔ {c['chave']}: {st['tentativas']} falhas — não é azar, é conteúdo. Reescreva a cena. ({st.get('erro', '')[:120]})")
                continue
            enviar(c)
        if not em_voo:
            break
        for k in list(em_voo):
            st = em_voo[k]
            try:
                status, motivo = gerador.checar_video(st["op"], pastas.clipe(k))
            except Exception as e:
                status, motivo = "rodando", None
                _log(f"  … erro no poll de {k} (tento de novo): {e}")
            if status == "pronto":
                st.update(status="pronto", clipe=pastas.clipe(k))
                del em_voo[k]
                _log(f"  ✓ pronto {k}")
            elif status == "falhou":
                st.update(status="falhou", erro=str(motivo)[:300])
                del em_voo[k]
                _log(f"  ✗ falhou {k}: {motivo}")
                if k in por_chave and st.get("tentativas", 0) < max_tentativas:
                    pendentes.append(por_chave[k])  # retry automático da cena isolada
            estado.salvar()
        if not esperar:
            break
        if em_voo:
            time.sleep(intervalo_poll)


def resumo(leva, estado):
    cont = {}
    for ad in leva["ads"]:
        for c in ad["cenas"]:
            s = estado.dados["cenas"].get(c["chave"], {}).get("status", "pendente")
            cont[s] = cont.get(s, 0) + 1
    return cont


def listar_falhas(leva, estado):
    out = []
    for ad in leva["ads"]:
        for c in ad["cenas"]:
            st = estado.dados["cenas"].get(c["chave"], {})
            if "falhou" in st.get("status", ""):
                out.append(f"{ad['id']} cena {fmt_n(c['n'])}: {st.get('erro', '')[:140]}")
    return out
