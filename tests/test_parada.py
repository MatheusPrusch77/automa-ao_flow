import pytest
from fabrica import leva as L, producao
from fabrica.estado import Estado, Pastas
import json
class Quebrado:
    n=0
    def imagem(self, *a):
        Quebrado.n+=1; raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
def test_para(tmp_path):
    d=json.load(open('exemplos/leva-exemplo.json'))
    leva,_=L.normalizar(d); pastas=Pastas(tmp_path).criar()
    for pk in ("ana","carlos"):
        open(pastas.master(pk),"wb").write(b"x")
    with pytest.raises(SystemExit) as e:
        producao.fase_frames(leva,pastas,Estado(pastas.estado),Quebrado(),pausa=0)
    assert Quebrado.n==3 and "429" in str(e.value)
