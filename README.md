# Fábrica de criativos com avatar (local)

Automação local para produzir **criativos de vídeo em volume** com avatares realistas,
baseada no método do pacote *sistema-criativos-e-vsl*: gancho de choque separado, corpo
dinâmico (T/D/I/L), imagem-mestre travando o rosto, gates de qualidade e montagem
automática em 1080x1920.

```
leva.json ─► validar ─► masters ─🚦─► frames ─🚦─► vídeos ─► qa ─► montar ─► ritmo ─► finais/*.mp4
             (lint +     (rostos)     (1 por      (Veo i2v   (fala,   (corte, punch-in,  (trocas/min,
             tabela)                  cena)       com fala)  frame)   gancho, legenda,   plano parado)
                                                                      headline, CTA)
```

🚦 = gate humano: você olha a grade e aprova antes de gastar geração de vídeo.

## Três formas de gerar (o resto do pipeline é idêntico)

| gerador | como funciona | custo | quando usar |
|---|---|---|---|
| **Flow manual-assistido** | a fábrica gera um pacote HTML com cada prompt pronto + nome do arquivo; você gera no Flow e baixa; `ingerir` puxa tudo pra leva | sua assinatura do Flow | usar os avatares que você já cria no Flow |
| **`--gerador veo`** | API oficial do Google (Nano Banana + Veo 3.1), 100% automático | por segundo de vídeo | volume alto sem ficar na frente da tela |
| **`--gerador simulado`** | clipes falsos, locais | zero | testar o pipeline, a montagem e as réguas |

> **Por que não o "driver sem clique" do pacote?** Ele contorna o reCAPTCHA do Flow
> (colhe o token do app e aborta a chamada) para disparar geração em lote numa conta de
> consumidor. Isso vai contra os termos do Flow e o próprio pacote avisa que volume em
> rajada derruba conta. Aqui a automação total vai pela API oficial; o Flow entra no modo
> assistido. Detalhes em [`docs/DO-PACOTE-PARA-A-FABRICA.md`](docs/DO-PACOTE-PARA-A-FABRICA.md).

## Instalação

```bash
python3 -m pip install -r requirements.txt   # Pillow, numpy, google-genai
# ffmpeg COM libass (legenda queimada):  brew install ffmpeg  |  apt install ffmpeg  |  winget install ffmpeg
python3 -m pip install faster-whisper          # opcional, recomendado: corte por fala, legenda sincronizada e QA de fala
```

Para a API do Veo: crie uma chave no Google AI Studio e exporte `GEMINI_API_KEY=...`
(ou use Vertex AI: `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`).
Modelos trocáveis por `FABRICA_MODELO_IMAGEM` e `FABRICA_MODELO_VIDEO`.

## Passo a passo

```bash
# 1. criar a leva (copia o modelo) e escrever personas, ganchos e cenas
python3 -m fabrica nova levas/2026-09-25
python3 -m fabrica validar levas/2026-09-25          # erros travam; avisos apontam leva "parada"
python3 -m fabrica validar levas/2026-09-25 --prompts  # ver todos os prompts

# 2A. modo Flow manual-assistido
python3 -m fabrica pacote-flow levas/2026-09-25       # abre levas/…/pacote-flow/index.html
python3 -m fabrica ingerir levas/2026-09-25 --tipo masters --de ~/Downloads
python3 -m fabrica ingerir levas/2026-09-25 --tipo clipes  --de ~/Downloads   # casa por nome (AD-01_3.mp4)
python3 -m fabrica ingerir levas/2026-09-25 --tipo clipes  --de ~/Downloads --por-ordem            # mostra o mapeamento
python3 -m fabrica ingerir levas/2026-09-25 --tipo clipes  --de ~/Downloads --por-ordem --confirmar

# 2B. modo API (automático)
python3 -m fabrica masters levas/2026-09-25 --gerador veo   # → qa/GRADE-MASTERS.jpg
python3 -m fabrica aprovar levas/2026-09-25 masters
python3 -m fabrica frames  levas/2026-09-25 --gerador veo   # → qa/GRADE-FRAMES.jpg
python3 -m fabrica aprovar levas/2026-09-25 frames
python3 -m fabrica videos  levas/2026-09-25 --gerador veo --max 4

# 3. qualidade e montagem (os dois modos)
python3 -m fabrica qa     levas/2026-09-25     # integridade, frame-0 × frame-base, whisper × roteiro
python3 -m fabrica montar levas/2026-09-25     # → finais/AD-01.mp4 …
python3 -m fabrica ritmo  levas/2026-09-25/finais
python3 -m fabrica status levas/2026-09-25
python3 -m fabrica refazer levas/2026-09-25 AD-03_1 --frame   # regerar só uma cena
```

Tudo é **idempotente**: rodar uma fase de novo pula o que já existe. O estado vive em
`estado.json` dentro da leva — se algo cair no meio, é só rodar de novo.

### Usar um avatar que você já criou no Flow

Baixe a imagem do avatar e aponte na persona — ela vira o master e nada é gerado:

```json
"personas": {
  "ana": { "master_arquivo": "avatares/ana.png", "cenario": "…", "voz": "woman around 32, …" }
}
```

## Estrutura da leva

```
levas/<nome>/
  leva.json        ← você (ou o Claude) escreve: personas, ganchos, cenas
  estado.json      ← a fábrica mantém
  masters/  frames/  clips/        ← imagens-mestre, frames de cena, clipes de 8s
  qa/              ← TABELA-PROVA.md, GRADE-*.jpg, GATE-CLIPES.json
  finais/          ← os criativos prontos
  pacote-flow/     ← modo manual
```

Formato completo do `leva.json` e as regras que o validador aplica:
[`docs/FORMATO-LEVA.md`](docs/FORMATO-LEVA.md). Próximas etapas da construção:
[`docs/ROTEIRO.md`](docs/ROTEIRO.md).

## Testes

```bash
python3 -m pytest -q            # inclui um ponta a ponta com o gerador simulado (~30s)
python3 -m pytest -q -m "not lento"
```

## Uso responsável

Avatares de IA fotorrealistas em anúncio: não os apresente como clientes reais dando
depoimento, não use rosto/nome de pessoa real, e siga as regras de rótulo de conteúdo
gerado por IA da plataforma onde o anúncio roda (Meta, TikTok, Google) e as normas de
publicidade (CONAR / CDC).
