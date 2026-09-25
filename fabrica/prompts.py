"""Montagem dos prompts (imagem-mestre, frame de cena e vídeo).

As regras vêm do pacote "sistema-criativos-e-vsl" (docs 01-CRIATIVOS/07 e 08 e o
catálogo de defeitos): prompt visual 100% em inglês, curto (< ~600 chars), aberto na
AÇÃO, sem redescrever a pessoa quando há imagem de referência, sem nomear câmera,
sem texto no quadro, e a MESMA descrição de voz em todas as cenas da persona.
"""

BLOCOS = {
    "REALISMO": ("Ultra-realistic smartphone footage look: real skin texture with pores, no beauty filter, "
                 "no CGI or advertising polish, real lighting consistent with the scene."),
    "TEXTRULE": ("No text, letters, captions, logos, watermarks, posters with words, screens or phone displays "
                 "anywhere in the frame. All surfaces are blank."),
    "FRAME": ("Full-bleed vertical 9:16 image edge to edge: no phone frame, no mockup, no letterboxing, "
              "no blurred bands, no smaller inset picture."),
    "POSE": ("Fixed, locked-off frame, nobody holding the camera, no selfie arm. Only ONE object is handled in this clip; "
             "every action has a visible destination inside the frame."),
    "NOFADE": ("Single continuous take, the action and the speech are already in motion at second zero. "
               "No fade in, no fade out, no slow motion, no camera movement. Hard cut at the end."),
    "LOOK": ("polished photo-ready look: styled hair, natural but visibly done makeup, an elegant confident presence, "
             "realistic skin texture with visible pores and slight natural asymmetry"),
    "CRITICAL": ("The room is EMPTY of any recording equipment: no camera, no tripod, no light stand, no microphone, "
                 "no phone, no tablet, no laptop, no screen. An anonymous face that does not resemble anyone famous."),
}

NEGATIVO_VIDEO = ("subtitles, text, watermark, letterboxing, blurred bands, extra hands, extra fingers, deformed hands, "
                  "objects duplicating or morphing, phone frame, mirror selfie, background music")

NOVO_ENQ = "DIFFERENT FRAMING FROM THE REFERENCE, FRAMING AND POSE ARE NEW."

# Tipo de cena do corpo (doc 08 §3) → o que entra no prompt.
TIPOS = {
    "T-close": f"Tight close-up: face and shoulders fill the whole frame. {NOVO_ENQ}",
    "T-aberto": f"Wide shot from the waist up, the whole setting visible around the person. {NOVO_ENQ}",
    "T-3/4": f"Three-quarter medium shot: the person stands at the left third of the frame, then looks into the lens. {NOVO_ENQ}",
    "T-cta": f"Medium shot, one arm fully extended pointing straight down at the bottom edge of the frame. {NOVO_ENQ}",
    "T": f"Medium shot. {NOVO_ENQ}",
    "D": "The demonstration with the object is the focus while the person keeps talking to the lens.",
    "I": "Photorealistic insert, hands and objects only, no face, no person visible.",
    "L": f"Same person, same outfit, in a DIFFERENT spot of the same setting. {NOVO_ENQ}",
}

MECANICAS = ("SPLIT", "INSERT_PRIMEIRO", "ACAO", "ESTRANHO")

GANCHO_ANCORA = ("SAME person as the reference (same face, hair, outfit and room), but NEW PROPS AND A NEW ACTION "
                 "are present and clearly visible. ")
GANCHO_FIM = f" {NOVO_ENQ} The props are the focus of the shot and must be plainly visible."

IDIOMAS = {"pt": "Brazilian Portuguese", "es": "Spanish", "en": "English", "fr": "French", "it": "Italian", "de": "German"}


def _frase(txt):
    txt = (txt or "").strip()
    return txt if not txt or txt[-1] in ".!?" else txt + "."


def prompt_master(persona):
    """Imagem-mestre: trava rosto + roupa + cenário da persona para o ad inteiro."""
    return " ".join([
        "Vertical 9:16 photo.",
        _frase(persona["descricao_visual"]),
        _frase(persona.get("cenario", "")),
        "Looking at the lens, relaxed natural expression, medium shot from the chest up, about to speak.",
        _frase(BLOCOS["LOOK"]) if persona.get("look", True) else "",
        BLOCOS["CRITICAL"], BLOCOS["REALISMO"], BLOCOS["TEXTRULE"], BLOCOS["FRAME"],
    ]).replace("  ", " ").strip()


def prompt_frame(cena, persona=None):
    """Frame inicial da cena, gerado com a imagem-mestre como referência (exceto inserts)."""
    tipo = cena.get("tipo") or ""
    acao = _frase(cena["acao"])
    if cena.get("gancho"):
        return f"Vertical 9:16 photo of the {GANCHO_ANCORA}{acao}{GANCHO_FIM}"
    if tipo == "I":
        cenario = _frase(persona.get("cenario", "")) if persona else ""
        return f"Vertical 9:16 photo. {TIPOS['I']} {acao} {cenario} {BLOCOS['TEXTRULE']}".replace("  ", " ").strip()
    extra = TIPOS.get(tipo, "")
    return (f"Vertical 9:16 photo of the SAME person as the reference (same face, hair, outfit and room). "
            f"{acao} {extra} {BLOCOS['TEXTRULE']}").replace("  ", " ").strip()


def prompt_video(cena, persona, idioma="pt"):
    """Prompt de image-to-video: ação + regras curtas + fala com a voz fixa da persona."""
    tipo = cena.get("tipo") or ""
    lingua = IDIOMAS.get(idioma, idioma)
    corpo = _frase(cena.get("prompt_video_custom") or cena["acao"])
    if tipo in TIPOS and tipo != "I" and not cena.get("gancho"):
        corpo += " " + TIPOS[tipo]
    regras = BLOCOS["NOFADE"] if tipo == "I" else f"{BLOCOS['POSE']} {BLOCOS['NOFADE']}"
    fala = (cena.get("fala") or "").strip()
    voz = (persona or {}).get("voz", "")
    if fala and tipo == "I":
        fala_blk = f'Off-camera narration in {lingua}, {voz}, no person visible, no other voices: "{fala}"'
    elif fala:
        fala_blk = f'The person speaks in {lingua} to the lens, {voz}, lips in sync, no other voices: "{fala}"'
    else:
        fala_blk = "No speech. Ambient sound only, no music."
    if fala and len(fala.split()) < 15:  # fala curta: sem isso o gerador inventa frases no tempo que sobra do clipe
        fala_blk += " The person says ONLY this sentence, then stops talking and silently continues the action."
    return f"{corpo} {regras} {fala_blk}".replace("  ", " ").strip()
