"""Geradores de imagem/vídeo plugáveis.

Todo gerador implementa:
  imagem(prompt, referencia, destino)        → grava um PNG em `destino` (referencia = PNG da imagem-mestre ou None)
  enviar_video(prompt, frame, destino)       → devolve um id de operação (str)
  checar_video(op_id, destino)               → ("pronto", None) | ("rodando", None) | ("falhou", motivo)
"""


def obter(nome, **kw):
    if nome == "simulado":
        from .simulado import GeradorSimulado
        return GeradorSimulado(**kw)
    if nome in ("veo", "veo-api", "api"):
        from .veo_api import GeradorVeoAPI
        return GeradorVeoAPI(**kw)
    raise ValueError(f"gerador desconhecido: {nome} (use 'veo' ou 'simulado'; o Flow manual usa os comandos pacote-flow/ingerir)")
