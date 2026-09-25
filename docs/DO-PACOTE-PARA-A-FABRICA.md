# Do pacote *sistema-criativos-e-vsl* para esta fábrica

O que foi absorvido do pacote, onde cada peça vive aqui, e o que mudou (e por quê).

## O pacote em uma página

Três máquinas: **criativos pagos** (espionagem na Ad Library → construtor de ads → receitas
de formato → geração no Flow → montagem + QA), **VSL** (engenharia reversa → roteiro →
geração → edição dinâmica) e **avatares orgânicos** (persona postando reels, funil
comentário → DM). Por baixo das três, a mesma fábrica de vídeo:

1. **Imagem-mestre (master)** por persona: trava rosto, roupa e cenário.
2. **Frame por cena** gerado com o master como referência (i2i).
3. **Clipe de 8s** por cena (image-to-video) com a fala embutida no prompt.
4. **Gates**: grade de rostos e de frames antes de animar; depois, por clipe, tamanho,
   frame-0 × frame-base e whisper × roteiro.
5. **Montagem**: corte do silêncio, punch-in, gancho por mecânica, concat por filtro,
   legenda com o texto do roteiro, headline, CTA, 1080x1920/24fps, checagem de integridade.
6. **Ritmo medido**: trocas de estímulo por minuto e maior plano parado.

As leis que mais pesam na qualidade (e que o validador desta fábrica aplica):
gancho como entregável separado com 4 mecânicas; corpo com tipo por cena (T/D/I/L) e
nunca 3 iguais seguidos; fala de 15-26 palavras por clipe (o gerador inventa fala no tempo
que sobra); prompt visual em inglês, curto e aberto na ação; voz descrita igual em todas
as cenas; master com roupa + cenário explícitos; sem nome de pessoa real, sem reticências,
sem travessão.

## Mapa: script do pacote → módulo aqui

| pacote | aqui | observação |
|---|---|---|
| `gerar_specs.py` | `fabrica/leva.py` + `fabrica/prompts.py` | mesmas regras; prompts mais curtos (o pacote mostrou que cabeçalho longo causa recusa) |
| `flow_driver.py` | `fabrica/geradores/veo_api.py` + `fabrica/producao.py` | API oficial em vez de injetar JS na aba do Flow |
| `flow_download.py` / `flow_foto_id.py` | `fabrica/flow_manual.py` (`ingerir`, `master_arquivo`) | você baixa do Flow; a fábrica organiza |
| `gate_frames.py` | `fabrica/qa.py` (`grade_*`) | |
| `gate_clipes.py` | `fabrica/qa.py` (`gate_clipes`) | similaridade de imagem por correlação em vez de SSIM |
| `montar_leva.py` + `banner.py` | `fabrica/montagem.py` + `fabrica/banner.py` | |
| `medir_ritmo.py` | `fabrica/ritmo.py` | mesmas réguas |
| `voz-unica.py`, VSL, orgânico, espionagem Apify | — | etapas futuras, ver `ROTEIRO.md` |

## O que mudou de propósito

**1. Sem o "driver sem clique" do Flow.** O driver do pacote injeta JavaScript na aba logada
e, desde que o Google ligou o reCAPTCHA no Flow, dispara uma interação-isca para colher o
token do próprio app, aborta essa chamada e reaproveita o token na geração em lote. Isso é
contornar a proteção anti-automação do serviço — contra os termos de uso, e o próprio
pacote registra que volume em rajada derruba conta. Em vez disso:
- **automação total** pela API oficial (Gemini API / Vertex AI), que existe para isso;
- **Flow no modo assistido**: a fábrica faz tudo em volta (prompts, nomes, ingestão, QA,
  montagem) e você gera no Flow como o produto foi feito para ser usado.

**2. Sem a fila `veo_3_1_i2v_lite_low_priority` "de custo zero".** Ela é da interface do Flow;
na API o custo é por segundo. Para comparar os dois caminhos: uma leva de 25 ads × ~8 clipes
= ~200 clipes de 8s. Consulte a tabela de preços atual do Veo (Fast é bem mais barato que o
de qualidade máxima) e faça as contas antes de escalar; o modo manual continua disponível
para quando o custo por clipe não compensar.

**3. Módulo orgânico fica de fora.** Uma parte dele ensina a montar páginas de persona de IA
sem que a plataforma perceba a rede coordenada. Isso não entra aqui. Os aprendizados
técnicos dele (identidade ≠ cena, legenda e voz) já estão incorporados.
