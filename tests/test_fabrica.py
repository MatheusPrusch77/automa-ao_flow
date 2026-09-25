import copy
import json
import os

import pytest

from fabrica import leva as L
from fabrica import montagem, transcricao
from fabrica.estado import Estado, Pastas
from fabrica.flow_manual import exportar_pacote, ingerir

AQUI = os.path.dirname(os.path.abspath(__file__))
EXEMPLO = os.path.join(os.path.dirname(AQUI), "exemplos", "leva-exemplo.json")
FALA_OK = "Esta é uma fala de teste com o tamanho certo para caber inteira num clipe de oito segundos sem sobrar tempo."


def _exemplo():
    with open(EXEMPLO, encoding="utf-8") as f:
        return json.load(f)


def test_exemplo_valida_sem_erros():
    leva, rel = L.normalizar(_exemplo())
    assert rel.ok, rel.texto()
    ad2 = leva["ads"][1]
    assert [c["chave"] for c in ad2["cenas"]][:2] == ["AD-02_0", "AD-02_1"]  # SPLIT gera insert (0) + gancho (1)
    assert not ad2["cenas"][0]["usa_master"] and ad2["cenas"][1]["usa_master"]
    assert "face fully in the upper half" in ad2["cenas"][1]["prompt_frame"]


@pytest.mark.parametrize("fala, trecho", [
    ("Curta demais.", "palavras (<15)"),
    ("Eu " + "muito " * 30 + "falei.", "(>26)"),
    (FALA_OK.replace(",", "") + " — e mais", "travessão"),
    (FALA_OK + " E então...", "reticências"),
])
def test_erros_de_fala(fala, trecho):
    d = _exemplo()
    d["itens"][0]["cenas"][0]["fala"] = fala
    _, rel = L.normalizar(d)
    assert any(trecho in e for e in rel.erros), rel.erros


def test_persona_sem_voz_e_placeholder():
    d = _exemplo()
    del d["personas"]["ana"]["voz"]
    d["itens"][0]["cenas"][1]["acao"] = "macro of {PRODUTO} on the counter"
    _, rel = L.normalizar(d)
    assert any("sem 'voz'" in e for e in rel.erros)
    assert any("placeholder" in e for e in rel.erros)


def test_avisos_de_dinamica():
    d = _exemplo()
    for c in d["itens"][0]["cenas"][:3]:
        c["tipo"] = "T-close"
    d["itens"][1]["gancho"]["persona"] = "ana"
    for c in d["itens"][1]["cenas"]:
        c["persona"] = "ana"
    _, rel = L.normalizar(d)
    txt = " ".join(rel.avisos)
    assert "3 cenas seguidas" in txt and "mesma persona" in txt


def test_prompt_visual_curto_e_sem_descricao_no_gancho():
    leva, _ = L.normalizar(_exemplo())
    g = leva["ads"][0]["cenas"][0]
    assert g["prompt_frame"].count("striking Brazilian woman") == 0  # o master já ancora quem é
    assert len(g["prompt_frame"]) < 700


def test_blocos_e_tempos_de_legenda():
    blocos = montagem.blocos_legenda(FALA_OK)
    assert all(1 <= len(b.split()) <= 5 for b in blocos)
    assert " ".join(blocos) == FALA_OK
    tempos = montagem.tempos_legenda(FALA_OK, 0.0, 6.0)
    assert tempos[0][1] == 0.0 and tempos[-1][2] == pytest.approx(6.0)
    assert all(a < b for _, a, b in tempos)


def test_similaridade_normaliza_numeros():
    assert transcricao.similaridade("tenho trinta anos de idade", "Tenho 30 anos de idade.") == 1.0
    assert transcricao.similaridade("uma frase completamente diferente aqui", "outra coisa sem relação nenhuma") < 0.6


def test_ingerir_por_nome_e_por_ordem(tmp_path):
    pastas = Pastas(tmp_path / "leva").criar()
    leva, _ = L.normalizar(_exemplo())
    dl = tmp_path / "Downloads"
    dl.mkdir()
    (dl / "flow_AD-01_2.mp4").write_bytes(b"x")
    (dl / "AD-01_10.mp4").write_bytes(b"x")  # não pode casar com AD-01_1
    plano, ok = ingerir(leva, pastas, str(dl), "clipes")
    assert ok and [p[1] for p in plano] == ["AD-01_2"]
    plano, ok = ingerir(leva, pastas, str(dl), "clipes", por_ordem=True)
    assert not ok and plano[0][1] == "AD-01_1"  # sem --confirmar só mostra


def test_pacote_flow(tmp_path):
    pastas = Pastas(tmp_path / "leva").criar()
    leva, _ = L.normalizar(_exemplo())
    html = open(exportar_pacote(leva, pastas), encoding="utf-8").read()
    assert "AD-02_0.png / AD-02_0.mp4" in html and "master ana" in html


def test_estado_persistente(tmp_path):
    e = Estado(str(tmp_path / "estado.json"))
    e.cena("AD-01_1").update(status="pronto")
    e.salvar()
    assert Estado(str(tmp_path / "estado.json")).cena("AD-01_1")["status"] == "pronto"


@pytest.mark.lento
def test_ponta_a_ponta_simulado_insert_primeiro(tmp_path, monkeypatch):
    # o áudio simulado são bipes, não fala: sem whisper o teste fica determinístico (e não depende de GPU/modelo)
    monkeypatch.setenv("SEM_WHISPER", "1")
    from fabrica import ritmo
    from fabrica.geradores.simulado import GeradorSimulado
    from fabrica.producao import fase_frames, fase_masters, fase_videos
    d = _exemplo()
    ad = copy.deepcopy(d["itens"][0])
    ad["gancho"]["mecanica"] = "INSERT_PRIMEIRO"
    ad["gancho"]["insert_visual"] = "macro: dozens of paper cups stacked in a tower on the counter"
    ad["cenas"] = ad["cenas"][:2]
    d["itens"] = [ad]
    pastas = Pastas(tmp_path / "leva").criar()
    leva, rel = L.normalizar(d)
    assert rel.ok, rel.texto()
    estado, g = Estado(pastas.estado), GeradorSimulado()
    fase_masters(leva, pastas, estado, g)
    fase_frames(leva, pastas, estado, g, pausa=0)
    fase_videos(leva, pastas, estado, g, intervalo_poll=0, pausa_envio=0)
    final = montagem.montar_ad(leva["ads"][0], pastas, "pt", montagem.Opcoes(min_dur=0), log=lambda *_: None)
    r = ritmo.medir(final)
    assert 1.6 + 3 * 5.5 < r["duracao"] < 1.6 + 3 * 6.5  # insert de 1,6s + 3 clipes com o silêncio do fim cortado
    assert r["silencios"] == 0


# ── gerador de leva (modelo soda) ────────────────────────────────────────────
MODELO_SODA = os.path.join(os.path.dirname(AQUI), "modelos", "soda.json")
AVATARES_TESTE = {"Ana": {"arquivo": "ana.png", "sexo": "f", "voz": "woman around 45, warm voice, natural American accent"},
                  "Bob": {"arquivo": "bob.png", "sexo": "m", "voz": "man around 50, deep voice, natural American accent"}}


def _modelo_soda():
    with open(MODELO_SODA, encoding="utf-8") as f:
        return json.load(f)


def test_modelo_soda_todas_as_falas_na_faixa():
    m = _modelo_soda()
    falas = [f for v in m["versoes"] for f in v["falas"]] + [m["cta_fala"]]
    assert all(len(v["falas"]) == 3 for v in m["versoes"])
    fora = [(L.palavras(f), f) for f in falas if not m["fala_min"] <= L.palavras(f) <= L.FALA_MAX]
    assert not fora, fora


def test_gerar_leva_valida_e_sem_repeticao(tmp_path):
    from fabrica.gerador_leva import gerar
    for nome in ("ana.png", "bob.png"):
        (tmp_path / nome).write_bytes(b"x")
    m = _modelo_soda()
    leva, novos = gerar(m, AVATARES_TESTE, por_avatar=3, semente=7, base_avatares=str(tmp_path))
    norm, rel = L.normalizar(leva)
    assert rel.ok and not rel.avisos, rel.texto()
    assert len(norm["ads"]) == 6 and all(len(ad["cenas"]) >= 4 for ad in norm["ads"])
    assert norm["ads"][0]["cenas"][-1]["fala"] == m["cta_fala"]  # CTA sempre na última cena, sozinho
    for pk in ("ana", "bob"):  # no mesmo dia: as 3 versões e 3 ganchos diferentes por avatar
        combos = novos[pk]
        assert len({c[0] for c in combos}) == 3 and len({c[1] for c in combos}) == 3
    leva2, novos2 = gerar(m, AVATARES_TESTE, 3, semente=7, historico=novos, base_avatares=str(tmp_path))
    for pk in novos:  # dia seguinte: nenhuma combinação repetida
        assert not {tuple(c) for c in novos[pk]} & {tuple(c) for c in novos2[pk]}
    assert "She" in leva["itens"][0]["gancho"]["acao_visual"] and "He" in leva["itens"][3]["gancho"]["acao_visual"]


def test_fala_curta_ganha_trava_no_prompt():
    leva, rel = L.normalizar({"idioma": "en", "fala_min": 8,
                              "personas": {"a": {"descricao_visual": "a woman in a red shirt", "cenario": "kitchen",
                                                 "voz": "woman around 40, warm voice"}},
                              "itens": [{"id": "X", "cenas": [{"n": 2, "tipo": "D", "persona": "a", "acao": "she stirs a glass",
                                                               "fala": "One teaspoon of baking soda, half a lemon, and a pinch of salt."}]}]})
    assert rel.ok, rel.texto()
    assert "says ONLY this sentence" in leva["ads"][0]["cenas"][0]["prompt_video"]


def test_corte_na_ultima_palavra_do_roteiro(monkeypatch):
    ws = [(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate("one two three four five extra words invented".split())]
    monkeypatch.setattr(montagem.transcricao, "palavras", lambda *a, **k: ws)
    monkeypatch.setattr(montagem.midia, "duracao", lambda *a: 8.0)
    ini, fim = montagem._fim_da_fala("x.mp4", "en", "one two three four five")
    assert ini == 0.0 and fim == pytest.approx(1.6 + 0.3 + 0.18)


def test_palavra_na_tela_acha_o_momento():
    fala = "Comment soda and I'll send it to you. Follow me first so I can reach you."
    t0, t1 = montagem.tempo_de_frase(fala, "follow me", 0.0, 8.0)
    assert 3.0 < t0 < t1 < 6.0
    ws = [(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(fala.split())]
    assert montagem.tempo_de_frase(fala, "soda", 0.0, 8.0, ws) == (0.4, 0.7)
    assert montagem.tempo_de_frase(fala, "banana", 0.0, 8.0) is None


def test_estilo_cru_no_formato_do_dono(tmp_path):
    from fabrica.gerador_leva import gerar
    (tmp_path / "ana.png").write_bytes(b"x")
    leva, _ = gerar(_modelo_soda(), {"Ana": AVATARES_TESTE["Ana"]}, por_avatar=1, semente=1, base_avatares=str(tmp_path))
    norm, rel = L.normalizar(leva)
    assert rel.ok, rel.texto()
    pv = norm["ads"][0]["cenas"][-1]["prompt_video"]
    for bloco in ("Character:", "Action:", "Voice:", "Audio:", "Dialogue:", "Constraints:"):
        assert bloco in pv
    assert "Comment soda" in pv
