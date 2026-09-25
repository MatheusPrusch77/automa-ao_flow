# Uso diário — molde "soda" (Windows / cmd)

Formato: vídeos de ~20s, 3 cenas de 8s (gancho → preparo → CTA), sem legenda e sem headline,
com **SODA** e **FOLLOW ME** saltando na tela no CTA. Cada avatar recebe 3 vídeos por dia,
com gancho, abertura e parte do corpo diferentes, sem repetir combinação de um dia para o outro.

## Uma vez só

1. Coloque as imagens dos avatares em `automa-ao_flow\avatares\` (ex.: `avatares\Alice.jpg`).
   A pasta fica fora do git.
2. Confira `exemplos\avatares.json`: nome, arquivo, sexo (`f`/`m`), voz e cenário de cada um.
   Para incluir um avatar novo, copie uma linha e ajuste. A `voz` precisa ficar sempre igual.

## Todo dia

Abra o cmd na pasta do projeto:

```cmd
cd %USERPROFILE%\Documents\automa-ao_flow
.venv\Scripts\activate
set PYTHONUTF8=1
```

**1. Gerar a leva do dia** (troque a data):

```cmd
python -m fabrica gerar-leva levas\2026-09-26
```

Só alguns avatares: `--so Alice,Frank`. Outro número por avatar: `--por-avatar 2`.

**2. Gerar o pacote do Flow e abrir:**

```cmd
python -m fabrica pacote-flow levas\2026-09-26
start levas\2026-09-26\pacote-flow\index.html
```

Para cada vídeo, o pacote mostra as cenas com os prompts prontos (botão copiar) e o nome do arquivo:
- **Frame** (imagem): no Flow, modo imagem, anexando a foto do avatar como referência. Os inserts
  (cena `_0`) vão sem referência.
- **Vídeo**: Frames para vídeo, com o frame como quadro inicial, 9:16.
- Salve com o nome indicado, ex.: `alice-1_1.png` e `alice-1_1.mp4`.

**3. Puxar os arquivos baixados:**

```cmd
python -m fabrica ingerir levas\2026-09-26 --tipo frames --de %USERPROFILE%\Downloads
python -m fabrica ingerir levas\2026-09-26 --tipo clipes --de %USERPROFILE%\Downloads
```

**4. Conferir e montar:**

```cmd
python -m fabrica qa levas\2026-09-26
python -m fabrica montar levas\2026-09-26
python -m fabrica ritmo levas\2026-09-26\finais
start levas\2026-09-26\finais
```

Montar um só: `--so alice-1`. Regerar uma cena ruim: `python -m fabrica refazer levas\2026-09-26 alice-1_2`,
gere de novo no Flow e rode `ingerir` + `montar --so alice-1`.

## Editar as copys e os ganchos

Tudo fica em `modelos\soda.json`: aberturas (com `{parte}`), partes do corpo, preparos, CTAs,
ganchos visuais (em inglês, abrindo na ação) e o que aparece na tela. Depois de editar, rode
`python -m pytest -q`: o teste confere se todas as falas ficaram entre 15 e 26 palavras.
