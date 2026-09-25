"""Elementos de tela que o gerador nunca desenha direito: faixa de headline e pílula de CTA com seta.
Tudo em PIL, com quebra de linha por LARGURA MEDIDA (nunca por contagem de caracteres) e
símbolos desenhados como polígono (glifo de sistema vira caixa vazia no vídeo)."""
import os

from PIL import Image, ImageDraw, ImageFont

ESTILOS = {  # fundo, texto
    "vermelho/branco": ((214, 30, 30), (255, 255, 255)),
    "amarelo/preto": ((255, 214, 0), (0, 0, 0)),
    "branco/preto": ((255, 255, 255), (0, 0, 0)),
    "preto/amarelo": ((0, 0, 0), (255, 214, 0)),
}
ROTACAO = list(ESTILOS)


def fonte(tam, bold=True):
    env = os.environ.get("FONT_BOLD" if bold else "FONT_REG")
    candidatas = [env] if env else []
    candidatas += (["/Library/Fonts/Arial Black.ttf", "/System/Library/Fonts/Supplemental/Arial Black.ttf",
                    "C:/Windows/Fonts/ariblk.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold else
                   ["/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for f in candidatas:
        if f and os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default()


def _quebra(d, texto, f, largura):
    linhas, atual = [], ""
    for p in texto.split():
        teste = f"{atual} {p}".strip()
        if d.textlength(teste, font=f) <= largura:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def headline(texto, estilo, destino, largura=1080, max_linhas=2):
    fundo, cor = ESTILOS.get(estilo, ESTILOS["vermelho/branco"])
    rascunho = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for tam in range(78, 30, -2):
        f = fonte(tam)
        linhas = _quebra(rascunho, texto.upper(), f, largura - 80)
        if len(linhas) <= max_linhas and all(rascunho.textlength(l, font=f) <= largura - 80 for l in linhas):
            break
    alt_linha = int(tam * 1.18)
    alt = alt_linha * len(linhas) + 44
    img = Image.new("RGBA", (largura, alt), fundo + (255,))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(linhas):
        w = d.textlength(l, font=f)
        d.text(((largura - w) / 2, 22 + i * alt_linha), l, font=f, fill=cor)
    img.save(destino)
    return destino, alt


def cta(texto, destino, largura=1080):
    f = fonte(62)
    rascunho = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    tw = rascunho.textlength(texto, font=f)
    pw, ph = int(tw + 110), 124
    alt = ph + 120
    img = Image.new("RGBA", (largura, alt), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0 = (largura - pw) // 2
    d.rounded_rectangle((x0 + 6, 8, x0 + pw + 6, ph + 8), radius=ph // 2, fill=(0, 0, 0, 120))
    d.rounded_rectangle((x0, 0, x0 + pw, ph), radius=ph // 2, fill=(255, 214, 0, 255), outline=(0, 0, 0, 255), width=5)
    d.text((x0 + 55, (ph - 72) // 2), texto, font=f, fill=(0, 0, 0))
    cx, top = largura // 2, ph + 18  # seta para baixo (polígono)
    d.polygon([(cx - 26, top), (cx + 26, top), (cx + 26, top + 44), (cx + 56, top + 44), (cx, top + 98),
               (cx - 56, top + 44), (cx - 26, top + 44)], fill=(255, 214, 0, 255), outline=(0, 0, 0, 255))
    img.save(destino)
    return destino, alt
