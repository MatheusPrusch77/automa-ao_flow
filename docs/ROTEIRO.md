# Roteiro de construção

## ✅ Etapa 1 — Fundação (esta entrega)

- [x] `leva.json` com personas, gancho separado e cenas tipadas; validador com erros e avisos
- [x] Prompts de master, frame e vídeo seguindo as leis do pacote
- [x] Estado em disco, fases idempotentes e retomáveis, gates de aprovação
- [x] Geradores: API oficial (Nano Banana + Veo), simulado; modo Flow manual-assistido (pacote HTML + `ingerir`)
- [x] QA de clipes (integridade, frame-0 × frame-base, whisper × roteiro, fala inventada)
- [x] Montagem: corte de silêncio, punch-in, SPLIT / INSERT_PRIMEIRO, legenda do roteiro, headline, CTA
- [x] Medidor de ritmo
- [x] Testes (incluindo ponta a ponta com o gerador simulado)

## Etapa 2 — Primeira leva real

1. Instalar ffmpeg + `faster-whisper` na sua máquina e rodar `python3 -m pytest -q`.
2. Escolher o caminho de geração (Flow manual ou API) e fazer **1 ad** completo.
3. Ajustar o que só aparece com clipe de verdade: enquadramento do split, tamanho da legenda,
   corte do fim da fala, recorte da marca-d'água (`--crop-wm`).
4. Registrar cada erro novo como regra no validador ou na montagem.

## Etapa 3 — Escrita da leva em volume

- Gerador de `leva.json` a partir de um briefing (oferta, nicho, público, provas) usando o
  Claude: tabela-prova primeiro, você aprova, depois o JSON.
- Variações: mesmo corpo com N ganchos (teste de gancho) ou mesmo gancho com N corpos.
- Biblioteca de personas reutilizáveis (`avatares/` + `personas.json`).

## Etapa 4 — Escala da produção

- Fila com várias levas, relatório por leva (tempo, falhas, custo estimado).
- Retry com reescrita assistida quando uma cena falha 3× (é conteúdo, não azar).
- Corte por fala palavra a palavra (gap > 0,55s) com whisper.
- Variante 4:5 / 1:1 além do 9:16.

## Etapa 5 — Inteligência de mercado (opcional)

- Espionagem da Ad Library via Apify (download, transcrição, frames) → dossiê do nicho.
- Registro de desempenho por ad para alimentar a próxima leva.
