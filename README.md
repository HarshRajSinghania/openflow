# OpenFlow

[![MIT](https://img.shields.io/github/license/codexfast/openflow)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)](pyproject.toml)
[![Estrelas no GitHub](https://img.shields.io/github/stars/codexfast/openflow?style=flat)](https://github.com/codexfast/openflow/stargazers)

OpenFlow é um projeto open source que permite usar os recursos do Google Flow disponíveis na sua assinatura Google AI Pro por meio de um servidor **MCP** ou de uma **API REST**.

Agentes de IA e aplicações podem gerar imagens e vídeos usando sua conta e os créditos do plano, sem enviar cada pedido manualmente na interface do Flow. O projeto também oferece operações de projetos, upload, upscale e download.

A integração usa uma sessão autenticada em um Chromium gerenciado, com perfil local persistente. O login é feito manualmente no navegador; depois, o servidor pode reutilizar a sessão em headless. **Não é necessário instalar extensão.**

> **Não é uma API oficial do Google.** O projeto utiliza interfaces internas do Flow e não tem afiliação ou endosso do Google. A automação pode contrariar termos ou políticas do serviço e resultar em restrições, suspensão ou banimento da conta. Use por sua conta e risco. Acesso, modelos e créditos continuam sujeitos ao plano e à disponibilidade do serviço.

O backend de navegador gerenciado é experimental. Mudanças no Flow podem interromper a integração.

## Índice

- [Funcionalidades](#features)
- [Requisitos](#requisitos)
- [Instalação e login](#setup)
- [Uso com MCP](#mcp)
- [Uso com REST](#rest)
- [Como funciona](#architecture)
- [Segurança, conta e créditos](#security)
- [Compatibilidade e limitações](#compatibilidade-e-limitações)
- [Exemplo de geração](#exemplo-de-geração)
- [Solução de problemas](#solução-de-problemas)
- [Desenvolvimento](#desenvolvimento)
- [Contribuição](#contribuição)
- [Contribuidores](#contribuidores)
- [Histórico de estrelas](#histórico-de-estrelas)
- [Backend legado](#backend-legado-extensão)
- [Créditos e licença](#créditos-e-licença)

<a id="features"></a>
## Funcionalidades

| Recurso | Suporte |
| --- | --- |
| **Imagens** | Nano Banana Pro, Nano Banana 2.1 e Nano Banana Lite |
| **Proporções de imagem** | `1:1`, `9:16`, `16:9`, `3:4`, `4:3`; até 4 referências |
| **Vídeos Omni** | Texto, quadro inicial, inicial/final ou até 3 referências; 4, 6, 8 ou 10 s; 360p/720p |
| **Vídeos Veo Lite** | Quadro inicial obrigatório, 8 s, 720p |
| **Upscale** | Imagens 2K/4K conforme conta/plano; 4K exige Ultra. Vídeos 1080p com `scene_id` real |
| **Projetos e mídia** | Listagem e criação de projetos, upload, consulta de jobs e download |
| **Integrações** | MCP stdio/HTTP e REST com schemas OpenAPI |
| **Controle** | Prévia/confirmação, contexto de projeto/documento e jobs persistentes em SQLite |

Os modelos e recursos disponíveis dependem da conta e do plano. O nome Nano Banana 2.1 corresponde ao identificador `nano_banana_2` nos parâmetros da API.

## Requisitos

- Python 3.11 ou superior e [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Conta Google com acesso ao [Flow](https://flow.google.com/), como o oferecido pela assinatura Google AI Pro.
- Créditos e acesso aos modelos necessários para cada operação, conforme o plano.
- Ambiente com interface gráfica para o login inicial; depois, o navegador pode operar em headless.
- Cliente compatível com MCP ou aplicação que faça chamadas HTTP à API REST.

O Chromium dedicado é instalado nos passos abaixo. Não é necessário instalar uma extensão ou compartilhar o perfil pessoal do navegador.

<a id="quick-start"></a>
<a id="setup"></a>
## Instalação e login

### 1. Instalar dependências

```bash
git clone https://github.com/codexfast/openflow.git
cd openflow
uv sync --extra browser
uv run --extra browser playwright install chromium --no-shell
```

No Linux, o Playwright também exige bibliotecas de sistema compatíveis. Se faltarem dependências, consulte as [instruções do Playwright](https://playwright.dev/python/docs/browsers#install-system-dependencies). Os comandos acima não instalam pacotes do sistema com privilégios administrativos.

### 2. Autenticar no Flow

```bash
uv run --extra browser openflow setup
```

Uma janela do Chromium será aberta. **Faça login diretamente no Google e abra o Flow.** Senha e 2FA são informados somente no site, nunca ao agente ou ao OpenFlow.

Feche a janela ou pressione Ctrl+C para encerrar o setup e liberar o perfil. O login fica salvo no perfil dedicado; se a sessão expirar, repita o setup.

### 3. Iniciar MCP ou REST

| Agente com ferramentas MCP | Aplicação ou script via REST |
| --- | --- |
| Configure o cliente para executar o comando abaixo em stdio. | Execute a API e abra `http://127.0.0.1:8100/docs`. |
| `uv run --extra browser openflow` | `uv run --extra browser openflow-api --api-port 8100` |
| [Configuração MCP →](#mcp) | [Exemplo REST →](#rest) |

**O servidor inicia o navegador headless automaticamente.** Não deixe `setup` ou `browser start` aberto em paralelo. MCP e REST são alternativas: execute um por vez com o mesmo perfil.

<a id="clients"></a>
<a id="mcp"></a>
## Integração MCP

OpenFlow é um **servidor de ferramentas MCP**, não um provedor de chat ou uma API compatível com OpenAI. Use um cliente com suporte a ferramentas MCP, como OpenCode, Claude Code, Codex, Cursor, Cline ou Hermes Agent. Cada cliente tem seu próprio formato de configuração.

### Exemplo: OpenCode

Substitua o caminho absoluto pelo diretório do clone. O cliente inicia o processo stdio; não abra outro servidor manualmente.

```json
{
  "mcp": {
    "openflow": {
      "type": "local",
      "command": [
        "uv", "--project", "/caminho/absoluto/openflow",
        "run", "--extra", "browser", "openflow"
      ],
      "enabled": true
    }
  }
}
```

Comando stdio para outros clientes:

```bash
uv --project /caminho/absoluto/openflow run --extra browser openflow
```

No Windows, use um caminho como `C:\\Projects\\openflow` no JSON.

### Ferramentas e sequência

1. `list_connections`: obtenha o `connection_id` do navegador gerenciado, sem pareamento.
2. `list_projects`: escolha o `project_id` desejado. A listagem retorna à home; faça isso **antes** da prévia, pois navegar invalida prévias de outro documento.
3. `generate_image`, `generate_video`, `upload` ou upscale com `confirm=false`: prepare a operação. A página entra no projeto antes de vincular a prévia.
4. Apresente as entradas ao usuário e aguarde aprovação.
5. Repita a chamada com as mesmas entradas, `confirm=true` e **`preview_id` igual ao `job_id` retornado na prévia**.
6. Consulte `get_job` com `refresh=true`, quando necessário, e use `download` após `completed`.

`create_project` também usa prévia e confirmação; após a criação, o navegador abre o novo projeto. `get_account_status` e `refresh_account` verificam a conta visível e consultam o saldo por HTTPS no navegador gerenciado, sem abrir painéis. O retorno informa `credits`, `credits_source` e `credits_freshness`; uma leitura indisponível retorna `null`, nunca um saldo estimado ou anterior.

### MCP via HTTP

Como alternativa ao stdio:

```bash
uv run --extra browser openflow --transport streamable-http --host 127.0.0.1 --mcp-port 8000
```

Endpoint: `http://127.0.0.1:8000/mcp`. Para clientes remotos, use túnel ou uma camada autenticada e transporte seguro. Não publique a porta diretamente na internet. O servidor deve ter acesso ao navegador, perfil e sessão do sistema operacional usados no login.

<a id="rest"></a>
## API REST

```bash
uv run --extra browser openflow-api --host 127.0.0.1 --api-port 8100
```

[Swagger UI](http://127.0.0.1:8100/docs) · [ReDoc](http://127.0.0.1:8100/redoc) · [OpenAPI](http://127.0.0.1:8100/openapi.json) — disponíveis enquanto a API local estiver executando.

### Exemplo: gerar e baixar uma imagem

Os comandos abaixo usam Bash, `curl` e `jq`. Execute em sequência no mesmo terminal. O exemplo não escolhe um projeto nem confirma uma geração automaticamente.

**1. Consulte a conexão e os projetos:**

```bash
BASE=http://127.0.0.1:8100
curl -fsS "$BASE/connections" | jq

# Copie o identificador retornado; substitua os placeholders.
CONNECTION_ID='<connection_id>'
curl -fsS --get "$BASE/projects" \
  --data-urlencode "connection_id=$CONNECTION_ID" | jq '.projects'
PROJECT_ID='<project_id>'
```

**2. Prepare uma prévia, sem gerar mídia:**

```bash
INPUT='{"prompt":"Portal circular de titânio e basalto, costa fantástica, água turquesa e luz âmbar","model":"nano_banana_2","ratio":"16:9","references":[]}'

BODY=$(jq -n --arg c "$CONNECTION_ID" --arg p "$PROJECT_ID" --argjson i "$INPUT" \
  '{connection_id:$c, project_id:$p, input:$i, confirm:false}')
PREVIEW=$(curl -fsS "$BASE/images" -H 'Content-Type: application/json' -d "$BODY")
printf '%s\n' "$PREVIEW" | jq
PREVIEW_ID=$(printf '%s' "$PREVIEW" | jq -er 'select(.state == "preview") | .job_id')
```

**3. Somente após conferir a prévia e obter aprovação humana**, execute o bloco separado abaixo. Pode consumir créditos. Não altere `BODY`, não liste projetos nem mude o documento entre a prévia e a confirmação.

```bash
CONFIRM=$(printf '%s' "$BODY" | jq --arg id "$PREVIEW_ID" \
  '.confirm = true | .preview_id = $id')
RESULT=$(curl -fsS "$BASE/images" -H 'Content-Type: application/json' -d "$CONFIRM")
printf '%s\n' "$RESULT" | jq '{job_id, state}'
JOB_ID=$(printf '%s' "$RESULT" | jq -er '.job_id')
```

**4. Consulte o job, sem reenviar a geração:**

```bash
curl -fsS --get "$BASE/jobs/$JOB_ID" \
  --data-urlencode "connection_id=$CONNECTION_ID" \
  --data-urlencode "project_id=$PROJECT_ID" \
  --data-urlencode 'refresh=true' | jq '{job_id, state}'
```

Se estiver `pending`, consulte novamente mais tarde. **`submitted_unverified` não significa falha:** verifique o job e o projeto manualmente antes de qualquer nova submissão.

**5. Apenas após `completed`, baixe o resultado:**

```bash
# Caminho absoluto na máquina do servidor; pasta existente e arquivo ainda inexistente.
DESTINATION='/caminho/absoluto/resultado.jpg'
jq -n --arg c "$CONNECTION_ID" --arg p "$PROJECT_ID" --arg d "$DESTINATION" \
  '{connection_id:$c, project_id:$p, destination:$d, asset_index:0}' |
  curl -fsS "$BASE/jobs/$JOB_ID/download" -H 'Content-Type: application/json' --data-binary @-
```

O download aceita somente resultados de um job concluído e do escopo correspondente. No upscale de imagem, o Flow pode devolver a imagem embutida em vez de um asset com URL: nesse caso, `result.inline_image_available` e `result.download_available` são `true`; use o mesmo endpoint de download com `asset_index: 0`, mesmo com `assets: []`. O retorno do download inclui a resolução solicitada e as dimensões observadas, quando disponíveis; isso não comprova qualidade visual. Não recebe uma URL arbitrária nem sobrescreve arquivos existentes.

### Endpoints principais

| Método | Rota | Finalidade |
| --- | --- | --- |
| `GET` | `/health` | Estado do serviço |
| `GET` | `/connections` | Conexões disponíveis |
| `GET` | `/connections/{connection_id}` | Contexto do navegador |
| `GET` | `/connections/{connection_id}/account` | Evidências de conta; `refresh=true` para atualizar |
| `GET` | `/projects` | Listar projetos com `connection_id` |
| `POST` | `/projects` | Preparar ou confirmar criação de projeto |
| `POST` | `/images`, `/videos` | Preparar ou confirmar geração |
| `POST` | `/images/upscale`, `/videos/upscale` | Preparar ou confirmar upscale |
| `POST` | `/uploads` | Preparar ou confirmar upload PNG/JPEG/WebP, até 8 MiB |
| `GET` | `/jobs/{job_id}` | Consultar ou atualizar job com conexão/projeto |
| `POST` | `/jobs/{job_id}/download` | Salvar resultado na máquina do servidor |

Os schemas completos e endpoints de compatibilidade estão no OpenAPI local. Não publique respostas com URLs assinadas, dados privados ou informações de conta.

<a id="architecture"></a>
## Como funciona

```text
  Agente MCP                     Aplicação REST
      │                                │
      ▼                                ▼
 Servidor MCP                     API FastAPI
      └────────────────┬───────────────┘
                       ▼
             Operações + jobs SQLite
                       │
                       ▼
          Chromium dedicado e gerenciado
             Sua sessão autenticada
                       │
              HTTPS no projeto do Flow
                       ▼
             Imagens · Vídeos · Assets
```

- **Sem extensão no fluxo padrão.** O OpenFlow usa um navegador próprio com perfil persistente, sem compartilhar seu perfil pessoal.
- **Sem cliques de geração.** As operações são chamadas HTTPS no contexto autenticado; a navegação abre o projeto solicitado antes de preparar a prévia.
- **Projeto obrigatório.** A confirmação exige os mesmos dados, projeto e documento da prévia. Se o contexto mudar, prepare uma nova prévia; o sistema não navega para ressuscitar a anterior.
- **Submissões incertas.** Jobs de resultado incerto ficam identificados para verificação, não são automaticamente ressubmetidos.

<a id="security"></a>
## Segurança, conta e créditos

- **Créditos.** OpenFlow não fornece créditos nem altera os limites da assinatura. Acesso, modelos e créditos são definidos pelo Google Flow. Confira custos na interface antes de confirmar; o sistema não garante leitura do saldo.
- **Prévia não é autorização.** Agentes e clientes devem apresentar as entradas e obter aprovação humana antes de executar operações confirmadas.
- **Resultado incerto não deve ser reenviado automaticamente.** Um timeout pode ocorrer depois de a operação ter sido aceita e consumido créditos.
- **Proteja o perfil persistente.** Ele contém cookies e dados que permitem acesso à conta. Não compartilhe, versione ou anexe a issues. O navegador usa perfil dedicado e não expõe uma porta TCP de depuração.
- **HTTP é acesso privilegiado.** A API REST não implementa autenticação HTTP própria, pode ler arquivos locais para upload e gravar downloads. Mantenha o serviço local; para acesso remoto, adicione controle de acesso e transporte seguro.
- **Nunca exponha credenciais.** Não publique senhas, cookies, tokens, URLs assinadas, bancos de jobs ou segredos legados em prompts, issues ou logs.
- **Respeite termos e direitos.** A licença do código não concede direitos sobre serviços ou resultados de terceiros.

### Perfil e renovação do login

No Linux, o perfil padrão fica em `~/.local/share/openflow/browser/profile`. Quando `LOCALAPPDATA` está definido, o diretório-base é `LOCALAPPDATA/openflow/browser` e o perfil fica em `profile/`.

Uma trava impede duas instâncias usando o mesmo perfil. Encerre MCP/REST antes de abrir setup ou diagnóstico. No Linux, o processo precisa acessar o keyring/DBus da sessão usada no login.

```bash
# Inspeciona o login salvo e encerra; não gera mídia.
uv run --extra browser openflow browser inspect

# Renova o login em uma janela normal, depois de encerrar o servidor.
uv run --extra browser openflow setup
```

`inspect` omite email, cookies e parâmetros da URL. `account_observed` indica evidência visível de conta, **não** acesso garantido à geração, plano ou créditos. Outros estados incluem `login_required`, `unknown` e `navigation_failed`. Diagnósticos não abrem painéis de conta.

## Compatibilidade e limitações

O projeto utiliza interfaces internas do Flow no contexto do navegador, não uma API pública estável de geração. Alterações no serviço, autenticação, reCAPTCHA, modelos ou planos podem interromper operações. Não há garantia de compatibilidade headless.

- Referências devem pertencer ao projeto e escopo correspondentes.
- Listar projetos retorna à home e pode invalidar prévias de outro documento.
- A troca de conta/documento exige nova prévia; não altere o contexto enquanto aguarda um resultado.
- O schema aceita upscale de imagem 2K/4K, mas disponibilidade depende da conta; 4K exige Ultra e não é garantido.
- Upscale de vídeo exige `scene_id` real; não invente identificadores.
- Veo Lite requer quadro inicial, 8 s e 720p. `veo_lite_low_priority` e `veo_fast_ultra` não são opções implementadas.
- O repositório não fornece imagem Docker ou Compose oficial. Um ambiente remoto precisa de navegador operacional, setup manual e acesso seguro ao perfil/keyring.

## Exemplo de geração

<details>
<summary>Imagem gerada via REST com Nano Banana 2.1</summary>

![Portal arquitetônico — imagem gerada por IA pelo OpenFlow](assets/flow-showcase/portal.jpg)

Nano Banana 2.1 (`nano_banana_2`), proporção `16:9`, saída de 1376 × 768. Gerada via REST no navegador gerenciado, sem extensão. É uma imagem estática gerada por IA, não uma fotografia ou vídeo.

Prompt resumido: portal circular de titânio e basalto sobre uma costa fantástica, água turquesa e luz âmbar. [Prompt completo e informações do arquivo](assets/README.md).

</details>

## Solução de problemas

| Sintoma | O que verificar |
| --- | --- |
| Chromium/Playwright ausente | Instale o extra `browser` e execute `playwright install chromium --no-shell` |
| Login indisponível ou expirado | Encerre o servidor e execute `openflow setup`; conclua verificações manualmente |
| Perfil em uso | Feche setup, diagnóstico ou outro MCP/REST que esteja usando o mesmo perfil; não remova o lock para forçar concorrência |
| Login salvo não reconhecido no Linux | Execute na sessão com acesso ao mesmo keyring/DBus usado no setup |
| Chromium não inicia no Linux | Confira as dependências de sistema exigidas pelo Playwright |
| `scope_changed` ou projeto divergente | Confira o projeto e prepare nova prévia; não reutilize confirmação de outro documento |
| `submitted_unverified` | Consulte o job e o projeto; não reenvie automaticamente |
| `rpc_rejected` | Confira entradas, modelo e recursos da conta; interfaces internas podem ter mudado |
| `native_recaptcha_automation_unsupported` | A integração esperada não está disponível; verifique a compatibilidade da versão e conclua desafios manuais pelo setup quando necessário |

## Backend legado: extensão

<details>
<summary><strong>Instalação e pareamento da extensão antiga — opcional, não necessário no fluxo padrão</strong></summary>

Este modo usa Google Chrome 116+ e a ponte WebSocket local na porta `9233`, em vez do navegador gerenciado.

1. Abra `chrome://extensions`, ative **Modo do desenvolvedor** e escolha **Carregar sem compactação** na pasta `extension/`.
2. Abra o Flow autenticado e o projeto desejado.
3. Inicie uma entrada explicitamente em modo legado:

```bash
# MCP stdio
uv run openflow --backend extension

# OU REST
uv run openflow-api --backend extension --host 127.0.0.1 --api-port 8100
```

4. Habilite a conexão no popup e compare o código antes de aprovar o pareamento.
5. No MCP, use `list_connections` / `list_pairing_requests`, depois `approve_connection` somente com confirmação humana do código.
6. Use `get_connection` e `select_flow_tab` para fixar o projeto/documento antes da prévia. Prévia e confirmação continuam obrigatórias.

REST mantém `/pairings`, `/pairings/{pairing_id}/approve` e `/connections/{connection_id}/select` para esse fluxo. Pareamento não substitui autenticação de acesso ao servidor HTTP.

Se não conectar, confira o servidor, popup e porta `9233`. Alterar a porta da ponte no servidor não reconfigura a extensão. Após atualizar a extensão, recarregue-a em `chrome://extensions` e recarregue a aba do Flow.

</details>

## Desenvolvimento

```text
src/flow_mcp/
├── cli.py             Setup e comandos de navegador
├── browser.py         Perfil, lock e sessão Chromium
├── managed.py         Backend sem extensão e contexto de projeto
├── server.py          Servidor MCP
├── api.py             API REST
├── service.py         Operações compartilhadas e downloads
├── manager.py         Conexões e escopo
├── jobs.py            Persistência SQLite
└── bridge.py          Ponte legada da extensão
extension/             Backend legado e runtime HTTPS compartilhado
tests/                 Testes Python
docs/                  Diagnósticos técnicos
assets/                Capa e demonstração gerada pelo OpenFlow
scripts/build_banner.py Composição reproduzível da capa
```

```bash
uv sync --extra browser --extra dev
uv run --extra browser --extra dev pytest
uv run --extra browser --extra dev ruff check .
uv run --extra browser --extra dev mypy
node --test extension/tests/*.test.mjs
```

Node.js é necessário apenas para os testes JavaScript. Testes reais de geração podem consumir créditos e exigem autorização.

## Contribuição

Contribuições de código, testes e documentação são bem-vindas. Mantenha as mudanças focadas, descreva passos de reprodução e execute as verificações pertinentes. Ao relatar problemas, inclua versões do Python, Playwright/Chromium e erros sanitizados; não envie dados de conta ou mídia privada.

## Contribuidores

[![Contribuidores do OpenFlow](https://contrib.rocks/image?repo=codexfast/openflow)](https://github.com/codexfast/openflow/graphs/contributors)

A lista é baseada nas contribuições registradas pelo GitHub. A atribuição do código original está na seção de créditos abaixo.

## Histórico de estrelas

[![Histórico de estrelas do OpenFlow](https://starchart.cc/codexfast/openflow.svg?variant=adaptive)](https://starchart.cc/codexfast/openflow)

## Créditos e licença

Este projeto deriva do código de **tuannguyenhoangit-droid**. A autoria original é reconhecida e o aviso de copyright permanece preservado:

```text
Copyright (c) 2026 tuannguyenhoangit-droid
```

Distribuído sob a [licença MIT](LICENSE), que permite uso, cópia, modificação, distribuição e uso comercial, inclusive venda, desde que sejam preservados os avisos exigidos pela licença. O software é fornecido sem garantias.

Google, Google Flow e os nomes dos modelos pertencem aos respectivos titulares. Sua menção descreve compatibilidade e não implica afiliação.

[Relatar bug ou propor melhoria](https://github.com/codexfast/openflow/issues) · [Contribuir](https://github.com/codexfast/openflow/pulls) · [Contribuidores](https://github.com/codexfast/openflow/graphs/contributors)
