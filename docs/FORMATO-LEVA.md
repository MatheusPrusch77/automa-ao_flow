# Formato do `leva.json`

Exemplo completo: [`exemplos/leva-exemplo.json`](../exemplos/leva-exemplo.json).

```jsonc
{
  "idioma": "pt",                 // idioma da FALA (pt, es, en…). Prompts visuais são sempre em inglês.
  "cta": "TOQUE E CONFIRA",       // texto da pílula de CTA (pode ser sobrescrito por ad)
  "personas": {
    "ana": {
      "descricao_visual": "…",    // quem é + ROUPA (cor e tecido) — em inglês
      "cenario": "…",             // lugar + luz — em inglês
      "voz": "woman around 32, warm mid-pitched voice, …",  // sexo + idade + timbre + ritmo, igual em todas as cenas
      "master_arquivo": "avatares/ana.png",  // opcional: imagem que você já criou no Flow (vira o master)
      "look": true                // opcional: false tira o bloco "polished photo-ready look" do master
    }
  },
  "itens": [
    {
      "id": "AD-01",
      "headline": "PROMESSA CONCRETA COM NÚMERO",   // ≤ ~46 caracteres
      "header_estilo": "vermelho/branco",          // vermelho/branco · amarelo/preto · branco/preto · preto/amarelo
      "gancho": {                                  // vira a cena 1 (e a 0, se houver insert)
        "mecanica": "SPLIT",                       // SPLIT · INSERT_PRIMEIRO · ACAO · ESTRANHO
        "persona": "ana",
        "acao_visual": "She …",                    // aberta na AÇÃO, sem redescrever a pessoa
        "insert_visual": "macro: …",               // obrigatório em SPLIT e INSERT_PRIMEIRO
        "gancho_fala": "…"                         // 15-26 palavras, fala no segundo zero
      },
      "cenas": [                                   // o corpo começa em n=2 (aceita 2.5 para intercalar)
        { "n": 2, "tipo": "T-close", "persona": "ana", "acao": "…", "fala": "…" },
        { "n": 3, "tipo": "I", "persona": "ana", "acao": "macro …", "fala": "…" }  // I = sem rosto, voz off
      ]
    }
  ]
}
```

## Tipos de cena do corpo

| tipo | o que é |
|---|---|
| `T-close` · `T-aberto` · `T-3/4` · `T-cta` · `T` | falando para a lente, cada um com enquadramento diferente |
| `D` | demonstrando o produto enquanto fala |
| `I` | insert sem rosto (mãos e objetos), a voz continua em off |
| `L` | mesma pessoa e roupa, em outro canto do mesmo cenário |

Nunca 3 do mesmo tipo seguidos. Pelo menos um `I` e um `D` por ad.

## Mecânicas de gancho (como a montagem trata)

| mecânica | clipes | montagem |
|---|---|---|
| `SPLIT` | pessoa (1) + insert (0) | pessoa em cima (1150px), insert embaixo (770px), áudio da pessoa |
| `INSERT_PRIMEIRO` | insert (0) + pessoa (1) | 1,6s do insert (áudio a 25%) e a pessoa entra falando |
| `ACAO` / `ESTRANHO` | pessoa (1) | o próprio clipe é o gancho |

Distribua as 4 pela leva (nenhuma acima de 40%).

## O que o validador faz

**Erros (a leva não roda):** persona inexistente ou sem `voz`; placeholder `{ASSIM}`;
fala com travessão ou reticências; fala fora de 15-26 palavras; `n` repetido; tipo ou
mecânica inválidos; SPLIT/INSERT_PRIMEIRO sem `insert_visual`; `master_arquivo` inexistente.

**Avisos (a leva roda, mas tende a sair fraca):** fala abaixo de 18 palavras; CAIXA ALTA na
fala; acento de português no prompt visual; persona sem roupa ou cenário explícito; ad sem
gancho; gancho abrindo com "the NN-year-old…" ou com instrução de montagem; 3 tipos iguais
seguidos; corpo sem `I` ou sem `D`; mesma persona em dois ads; mecânica dominando;
ganchos sem elemento de choque; `acao` acima de 600 caracteres.
