# Acerto de estoque BASF

Aplicação para processar o relatório de estoque do GIX, cruzá-lo com o mapeamento GIX/SKU da VTEX e gerar os arquivos de importação CSV e XLS legado. A API e o frontend são separados; a mesma rotina de negócio continua disponível pelo CLI.

## Arquitetura

- `backend/stock_processor.py`: regras de processamento e exportação, sem dependência da interface.
- `main.py`: execução local/CLI da rotina existente.
- `backend/app.py`: API Flask (`GET /api/health` e `POST /api/process`).
- `app.py`: entrypoint Flask reconhecido pela Vercel.
- `templates/` e `static/`: interface atendida pelo Flask, protegida pela mesma sessão cookie da API.
- `vercel.json`: configuração de execução da função Flask.
- `toolkit/gerar_csv_dict.py`: ferramenta existente para transformar `C.csv` em um mapeamento GIX/SKU.

O endpoint recebe o relatório GIX no campo `gix_file`. O mapeamento `mapping_file` é opcional; se omitido, usa `data/relacao_sku_basf_codigo_gix.csv`. A resposta contém a prévia e os dois arquivos em Base64. Os uploads e os arquivos temporários são descartados ao fim da requisição; o endpoint não sobrescreve os arquivos locais.

Para atualizar o mapeamento a partir de `C.csv`, a ferramenta legada `toolkit/gerar_csv_dict.py` continua disponível. Ela grava `relacao_sku_basf_codigo_gix.csv` na raiz; esse arquivo pode ser enviado na interface ou colocado em `data/` para uso como padrão.

## Regras de negócio

As regras preservadas estão descritas em [docs/REGRAS-DE-NEGOCIO.md](docs/REGRAS-DE-NEGOCIO.md). O processamento compartilhado pelo CLI e pela API usa os mesmos critérios de cruzamento, quantidades, campos VTEX e formatos de saída.

## Executar

Instale as dependências:

```powershell
python -m pip install -r requirements.txt
```

Para executar o fluxo CLI com os arquivos locais atuais:

```powershell
python main.py
```

Isso gera `files/output/estoque_vtex_basf.csv` e `files/output/estoque_vtex_basf.xls`.

## Controle de acesso

A aplicação exige senha antes de liberar a página, os arquivos frontend e os endpoints da API. Em desenvolvimento, copie `.env.example` para `.env`, defina sua senha em `APP_PASSWORD` e gere um valor para `SECRET_KEY` com:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

No deploy, defina `APP_PASSWORD` e `SECRET_KEY` nas Environment Variables do projeto Vercel (Production/Preview conforme necessário); não versione o arquivo `.env`. `COOKIE_SECURE` deve ficar `true` em produção HTTPS (na Vercel isso é automático) e pode ser `false` para desenvolvimento HTTP local.

Após login, o backend define um cookie de sessão Flask assinado, `HttpOnly`, `SameSite=Lax` e válido por 8 horas. O cookie contém apenas o estado autenticado, nunca a senha. A senha enviada no formulário é derivada com scrypt e comparada em tempo constante com o hash derivado da senha configurada no ambiente. Logout invalida a sessão.

Para executar a interface e a API localmente com o runtime da Vercel:

```powershell
npx vercel dev
```

Abra a URL informada pelo Vercel CLI. A senha é obrigatória também no endpoint `/api/health`, que pode ser verificado após login.

## Deploy na Vercel

Importe este repositório como projeto Vercel ou execute `npx vercel` na raiz. O runtime detecta o Flask exportado por `app.py`. Os templates e assets são incluídos na função e servidos por rotas Flask protegidas; eles não ficam no diretório público da CDN. Configure `APP_PASSWORD` e `SECRET_KEY` antes do deploy. O endpoint usa o mapeamento versionado como padrão, mas o relatório de estoque é enviado pelo usuário em cada processamento.

## Testes

```powershell
python -m unittest discover -s tests -v
```
