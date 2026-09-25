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
def test_ponta_a_ponta_simulado_insert_primeiro(tmp_path):
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
