"""Gerador falso, local e grátis: produz imagens e clipes sintéticos (8s, com 'fala' em bipes
e silêncio sobrando no fim, igual a um clipe de IA). Serve pra testar o pipeline inteiro —
QA, montagem, legenda, medidor de ritmo — sem gastar um centavo de crédito."""
import hashlib
import os

from PIL import Image, ImageDraw, ImageFont

from .. import midia


def _cor(txt):
    h = hashlib.md5(txt.encode()).digest()
    return (60 + h[0] % 160, 60 + h[1] % 160, 60 + h[2] % 160)


def _fonte(tam):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


class GeradorSimulado:
    def __init__(self, fala_seg=6.0, **_):
        self.fala_seg = fala_seg

    def imagem(self, prompt, referencia, destino):
        img = Image.new("RGB", (768, 1365), _cor(os.path.basename(destino)))
        d = ImageDraw.Draw(img)
        d.text((40, 60), os.path.basename(destino), font=_fonte(56), fill="white")
        y = 160
        for i in range(0, min(len(prompt), 520), 26):
            d.text((40, y), prompt[i:i + 26], font=_fonte(34), fill=(235, 235, 235))
            y += 44
        if referencia:
            ref = Image.open(referencia).resize((256, 455))
            img.paste(ref, (768 - 276, 1365 - 475))
        img.save(destino)

    def enviar_video(self, prompt, frame, destino):
        # "fala" = bipes alternados (som/pausa curta) por fala_seg, depois ~1,6s de silêncio (o que o corte precisa remover)
        fala = self.fala_seg
        audio = (f"sine=frequency=220:duration=8,volume='if(lt(t,{fala}),if(lt(mod(t,0.5),0.4),5,0),0)':eval=frame")
        entrada = ["-loop", "1", "-t", "8", "-i", frame] if frame else ["-f", "lavfi", "-t", "8", "-i", "color=c=gray:s=720x1280"]
        midia.run(entrada + ["-f", "lavfi", "-i", audio,
                             "-vf", "scale=720:1280,zoompan=z='1+0.0008*on':d=1:s=720x1280:fps=24,format=yuv420p",
                             "-t", "8", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", destino])
        return "simulado:" + os.path.basename(destino)

    def checar_video(self, op_id, destino):
        return ("pronto", None) if os.path.exists(destino) else ("falhou", "arquivo simulado sumiu")
