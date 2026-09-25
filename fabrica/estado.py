"""Estado da leva em disco (estado.json). O disco é a fonte da verdade:
toda fase é idempotente e retomável — rodar de novo pula o que já está pronto."""
import json
import os
import tempfile


class Pastas:
    def __init__(self, raiz):
        self.raiz = os.path.abspath(raiz)
        self.leva_json = os.path.join(self.raiz, "leva.json")
        self.estado = os.path.join(self.raiz, "estado.json")
        self.masters = os.path.join(self.raiz, "masters")
        self.frames = os.path.join(self.raiz, "frames")
        self.clips = os.path.join(self.raiz, "clips")
        self.qa = os.path.join(self.raiz, "qa")
        self.finais = os.path.join(self.raiz, "finais")
        self.trabalho = os.path.join(self.raiz, ".trabalho")
        self.pacote = os.path.join(self.raiz, "pacote-flow")

    def criar(self):
        for d in (self.masters, self.frames, self.clips, self.qa, self.finais, self.trabalho):
            os.makedirs(d, exist_ok=True)
        return self

    def master(self, persona):
        return os.path.join(self.masters, f"{persona}.png")

    def frame(self, chave):
        return os.path.join(self.frames, f"{chave}.png")

    def clipe(self, chave):
        return os.path.join(self.clips, f"{chave}.mp4")

    def final(self, ad_id):
        return os.path.join(self.finais, f"{ad_id}.mp4")


class Estado:
    def __init__(self, caminho):
        self.caminho = caminho
        self.dados = {"masters": {}, "cenas": {}}
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                self.dados = json.load(f)
            self.dados.setdefault("masters", {})
            self.dados.setdefault("cenas", {})

    def cena(self, chave):
        return self.dados["cenas"].setdefault(chave, {"status": "pendente", "tentativas": 0})

    def master(self, persona):
        return self.dados["masters"].setdefault(persona, {})

    def salvar(self):
        d = os.path.dirname(self.caminho)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.dados, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.caminho)
