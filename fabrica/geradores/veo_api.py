"""Gerador pela API OFICIAL do Google (Gemini API / Vertex AI): Nano Banana para imagem, Veo para vídeo.

É o caminho automatizável sem violar os termos do Flow: sem navegador, sem reCAPTCHA, sem risco
de bloquear a sua conta. Paga por segundo de vídeo gerado (veja a tabela de preços atual do Google).

Configuração (variáveis de ambiente):
  GEMINI_API_KEY=...                      (ou GOOGLE_API_KEY) — chave do Google AI Studio
  ou GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION   (Vertex AI)
  FABRICA_MODELO_IMAGEM=gemini-2.5-flash-image        (Nano Banana; troque pelo mais novo disponível)
  FABRICA_MODELO_VIDEO=veo-3.1-fast-generate-preview  (Veo 3.1 Fast; 'veo-3.1-generate-preview' = qualidade máxima)
"""
import io
import os

from ..prompts import NEGATIVO_VIDEO


class GeradorVeoAPI:
    def __init__(self, modelo_imagem=None, modelo_video=None, **_):
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise SystemExit("instale o SDK: pip install google-genai") from e
        self.types = types
        vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
        if not vertex and not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise SystemExit('❌ chave da API não encontrada. No cmd: setx GEMINI_API_KEY "SUA_CHAVE", '
                             "feche e abra o cmd de novo (a chave só vale nas janelas abertas depois do setx).")
        self.client = genai.Client()
        self.modelo_imagem = modelo_imagem or os.environ.get("FABRICA_MODELO_IMAGEM", "gemini-2.5-flash-image")
        self.modelo_video = modelo_video or os.environ.get("FABRICA_MODELO_VIDEO", "veo-3.1-fast-generate-preview")

    # ── imagem (master e frames de cena) ─────────────────────────────────────
    def imagem(self, prompt, referencia, destino):
        from PIL import Image
        t = self.types
        conteudo = [prompt]
        if referencia:
            conteudo.append(Image.open(referencia))
        resp = self.client.models.generate_content(
            model=self.modelo_imagem, contents=conteudo,
            config=t.GenerateContentConfig(response_modalities=["IMAGE"], image_config=t.ImageConfig(aspect_ratio="9:16")))
        for cand in resp.candidates or []:
            for parte in (cand.content.parts if cand.content else []) or []:
                if parte.inline_data and parte.inline_data.data:
                    Image.open(io.BytesIO(parte.inline_data.data)).convert("RGB").save(destino)
                    return
        motivo = getattr(resp, "prompt_feedback", None) or (resp.candidates[0].finish_reason if resp.candidates else "sem candidatos")
        raise RuntimeError(f"imagem recusada/vazia: {motivo}")

    # ── vídeo (image-to-video com fala nativa) ───────────────────────────────
    def enviar_video(self, prompt, frame, destino):
        t = self.types
        img = None
        if frame:
            with open(frame, "rb") as f:
                img = t.Image(image_bytes=f.read(), mime_type="image/png")
        op = self.client.models.generate_videos(
            model=self.modelo_video, prompt=prompt, image=img,
            config=t.GenerateVideosConfig(aspect_ratio="9:16", number_of_videos=1, negative_prompt=NEGATIVO_VIDEO))
        return op.name

    def checar_video(self, op_id, destino):
        t = self.types
        op = self.client.operations.get(t.GenerateVideosOperation(name=op_id))
        if not op.done:
            return "rodando", None
        if op.error:
            return "falhou", str(op.error)
        res = op.response or op.result
        vids = (res.generated_videos if res else None) or []
        if not vids:
            filtro = getattr(res, "rai_media_filtered_reasons", None) if res else None
            return "falhou", f"sem vídeo (filtro de conteúdo?): {filtro}"
        video = vids[0].video
        if not self.client.vertexai:
            self.client.files.download(file=video)
        video.save(destino)
        return "pronto", None
