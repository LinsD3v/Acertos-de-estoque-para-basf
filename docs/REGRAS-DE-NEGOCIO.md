# Regras de negócio atuais

Estas regras descrevem o processamento que existia no CLI antes da separação da camada web. `main.py` e a API chamam a mesma implementação em `backend/stock_processor.py`.

## Entradas e leitura

- O relatório do GIX usa separador `;` e contém o código GIX e a coluna de estoque atual.
- O mapeamento usa separador `;` e relaciona `GIX` a `SKU_VTEX`.
- O CLI lê `files/gix/Relatorio estoque basf.csv` e `data/relacao_sku_basf_codigo_gix.csv`. Na API, o relatório é enviado em cada requisição e o mapeamento pode ser enviado opcionalmente; sem mapeamento enviado, utiliza-se o arquivo do projeto.
- O utilitário legado `toolkit/gerar_csv_dict.py` transforma `C.csv` em um mapeamento com GIX, SKU VTEX e nome; ele permanece independente da aplicação web.
- A leitura tenta, nesta ordem, `utf-8-sig`, `cp1252` e `latin-1`.
- A identificação de cabeçalhos normaliza acentos e pontuação e mantém a correspondência aproximada já existente para tolerar cabeçalhos com caracteres corrompidos. Isso não altera nem aproxima a correspondência dos valores GIX.

## Cruzamento e estoque

- Os valores GIX são convertidos em texto e têm espaços externos removidos.
- O cruzamento é uma junção interna (`inner`) por igualdade exata entre GIX do relatório e GIX do mapeamento. Códigos sem correspondência são omitidos.
- SKU vazio, `NULL` ou `NAN` (sem distinção entre maiúsculas e minúsculas) é omitido.
- Estoque ausente/vazio ou não numérico resulta em `0`.
- Para estoque numérico, pontos são removidos como separadores de milhar, vírgula vira ponto decimal e o valor é convertido para `int` (truncamento da parte fracionária). Exemplo: `1.234,00` resulta em `1234`; `7,75` resulta em `7`.
- `SkuId` vem do mapeamento e é mantido como texto. A saída é ordenada numericamente por SKU, de forma estável, sem mudar o identificador.

## Campos enviados à VTEX

Além de `SkuId` e `TotalQuantity`, o arquivo mantém as colunas existentes nesta ordem:

`ReservedQuantity=0`, `AvailableQuantity=TotalQuantity`, `WarehouseId=1_1`, `WarehouseName=Estoque principal`, `RefId=0`, `IsActive=True`, `UnlimitedQuantity=False`, `LockIds` vazio e `DispatchedReservations=0`.

Não há chamada à API da VTEX: a aplicação apenas prepara os arquivos para importação manual.

## Controle de acesso web

- A página, assets do frontend e endpoints da API exigem uma sessão cookie autenticada. Apenas `/login` e o CSS necessário para exibir o formulário de login ficam públicos.
- A senha esperada vem de `APP_PASSWORD` no ambiente (ou `.env` local); `SECRET_KEY` assina a sessão do Flask e deriva o salt usado no hash scrypt.
- O cookie é `HttpOnly`, `SameSite=Lax`, `Secure` em produção HTTPS e expira após oito horas. Ele leva apenas o marcador de autenticação assinado, nunca a senha.
- Credenciais ausentes deixam a aplicação fechada e exibem erro de configuração; os uploads seguem temporários e não são persistidos.

## Exportação

- CSV separado por vírgula, com BOM UTF-8 e cabeçalho VTEX.
- XLS no formato legado Excel 97-2003, gerado com `xlwt`, aba `Estoque VTEX`; a coluna `SkuId` é escrita como texto.
- O CLI grava os dois arquivos em `files/output/`. A API gera os mesmos formatos em diretório temporário e devolve ambos para download, sem persistir os uploads no servidor.
