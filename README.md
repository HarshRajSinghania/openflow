# OpenFlow

**Google Flow no seu fluxo de trabalho: geração de imagens e vídeos via MCP e API REST.**

OpenFlow conecta agentes de IA e aplicações à sua sessão do Google Flow por meio de uma extensão Chrome e de um servidor Python local. Oferece prévias antes da execução, confirmação explícita e acompanhamento persistente de jobs.

Este projeto é baseado no código de **tuannguyenhoangit-droid**, cujo crédito e licença MIT original estão preservados em [LICENSE](LICENSE).

> Projeto independente, sem afiliação ou endosso do Google. A integração depende de interfaces internas do Flow e pode precisar de ajustes quando o serviço mudar. Gerações e upscales podem consumir créditos da sua conta.

## Índice

- [Recursos](#recursos)
- [Arquitetura](#arquitetura)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Integração MCP](#integração-mcp)
- [API REST](#api-rest)
- [Segurança e créditos](#segurança-e-créditos)
- [Compatibilidade e limitações](#compatibilidade-e-limitações)
- [Desenvolvimento](#desenvolvimento)
- [Solução de problemas](#solução-de-problemas)
- [Contribuições](#contribuições)
- [Créditos e licença](#créditos-e-licença)

## Recursos

| Recurso | Suporte documentado |
| --- | --- |
| Imagens | Nano Banana Pro, Nano Banana 2 e Nano Banana Lite |
| Proporções de imagem | `1:1`, `9:16`, `16:9`, `3:4` e `4:3` |
| Vídeos Omni | Texto, quadro inicial, inicial/final e referências; 4 a 10 segundos |
| Vídeos Veo Lite | Quadro inicial, 8 segundos, 720p |
| Upscale | Imagens em 2K e vídeos em 1080p nos cenários documentados |
| Integrações | MCP por stdio ou HTTP e API REST com OpenAPI |
| Operações auxiliares | Criação de projetos, upload, consulta de jobs e download |
| Controle de execução | Pareamento da extensão, seleção de aba e confirmação de prévias |
| Persistência | Jobs em SQLite e identificação de submissões não verificadas |

Consulte a [matriz de verificações](docs/matrix-verified.md) para cenários testados, restrições e estimativas de créditos. Esses registros não garantem disponibilidade em todas as contas.

## Arquitetura

```text
Agente MCP                 Cliente REST
    |                           |
    v                           v
Servidor MCP               API FastAPI
    |                           |
    +-------------+-------------+
                  |
          Operações + jobs SQLite
                  |
          Ponte WebSocket local
             127.0.0.1:9233
                  |
           Extensão Chrome
                  |
        Aba autenticada do Flow
```

O servidor roda na mesma máquina do Chrome. A extensão executa as operações no contexto da aba autenticada; o projeto não substitui a conta, o plano ou os créditos do Google Flow.

MCP e REST compartilham a camada de operações, mas são processos de entrada separados. Use um deles por vez com a configuração padrão: ambos iniciam a ponte na porta `9233`.

## Requisitos

- Python **3.11 ou superior**.
- `uv` para gerenciamento do ambiente, ou Python com `pip` em um ambiente virtual.
- Google Chrome **116 ou superior**.
- Conta com acesso ao Google Flow e créditos quando exigidos pela operação.
- Um cliente compatível com MCP, caso escolha essa integração.
- Node.js com suporte a `node --test` para executar os testes da extensão.

## Instalação

### 1. Preparar o ambiente

Na raiz do projeto:

```bash
uv sync --extra dev
```

Para instalar apenas as dependências de execução:

```bash
uv sync
```

Alternativamente, em um ambiente virtual já ativado:

```bash
python -m pip install -e ".[dev]"
```

### 2. Carregar a extensão

1. Abra `chrome://extensions` no Chrome.
2. Ative o **Modo do desenvolvedor**.
3. Escolha **Carregar sem compactação** e selecione a pasta `extension/`.
4. Abra [Google Flow](https://flow.google.com/) com sua conta autenticada e mantenha a aba aberta.
5. Configure e inicie uma das integrações abaixo.
6. No popup da extensão, habilite a conexão.
7. Compare o código de pareamento exibido na extensão antes de aprovar a conexão pelo cliente.

Se o Flow já estava aberto quando a extensão foi carregada ou atualizada, recarregue a página.

## Integração MCP

### Cliente local

Para um cliente como o OpenCode, adicione a configuração abaixo ao arquivo de configuração do cliente. Substitua o caminho absoluto pelo diretório deste projeto:

```json
{
  "mcp": {
    "openflow": {
      "type": "local",
      "command": [
        "uv",
        "--project",
        "/caminho/absoluto/openflow",
        "run",
        "openflow"
      ],
      "enabled": true
    }
  }
}
```

No Windows, use um caminho como `C:\\Projects\\openflow`. O cliente inicia o servidor em modo stdio; não é necessário abrir outro processo MCP manualmente.

Com `pip`, configure o cliente para executar o Python do ambiente virtual com os argumentos `-m flow_mcp.server`.

### Fluxo de uso

1. Consulte `list_connections` e `list_pairing_requests`.
2. Execute `approve_connection` somente após o usuário conferir o código da extensão.
3. Use `get_connection` e `select_flow_tab` para selecionar a aba e seu documento.
4. Solicite a operação, como `generate_image`, `generate_video` ou `upload`, com `confirm=false`.
5. Apresente a prévia ao usuário e aguarde aprovação.
6. Repita a operação com os mesmos dados, `confirm=true` e o `preview_id` retornado.
7. Consulte `get_job` com `refresh=true` e use `download` quando o resultado estiver disponível.

**Não reenvie automaticamente um job em `submitted_unverified`.** A submissão pode ter ocorrido mesmo sem confirmação de resposta, e uma nova tentativa pode gerar cobrança duplicada.

### Cliente em outra máquina

Na máquina do Chrome:

```bash
uv run openflow --transport streamable-http --host 0.0.0.0 --mcp-port 8000
```

No cliente MCP:

```json
{
  "mcp": {
    "openflow": {
      "type": "remote",
      "url": "http://<ip-da-maquina-do-chrome>:8000/mcp",
      "enabled": true
    }
  }
}
```

`0.0.0.0` expõe o serviço nas interfaces de rede da máquina. Restrinja o acesso no firewall a clientes confiáveis e use uma camada de autenticação e transporte seguro quando necessário. Não publique essa porta diretamente na internet.

## API REST

Como alternativa ao MCP, inicie a API na máquina do Chrome:

```bash
uv run openflow-api --host 127.0.0.1 --api-port 8100
```

Documentação local enquanto o servidor estiver em execução:

- Swagger UI: `http://127.0.0.1:8100/docs`
- ReDoc: `http://127.0.0.1:8100/redoc`
- OpenAPI: `http://127.0.0.1:8100/openapi.json`

### Principais endpoints

| Método | Rota | Finalidade |
| --- | --- | --- |
| `GET` | `/health` | Estado do serviço |
| `GET` | `/connections` | Conexões e pareamentos pendentes |
| `GET` | `/pairings` | Solicitações de pareamento |
| `POST` | `/pairings/{pairing_id}/approve` | Aprovar pareamento conferido pelo usuário |
| `GET` | `/connections/{connection_id}` | Consultar conexão e abas |
| `POST` | `/connections/{connection_id}/select` | Selecionar aba com `tab_id` |
| `GET` | `/connections/{connection_id}/account` | Consultar conta |
| `POST` | `/projects` | Preparar ou confirmar criação de projeto |
| `POST` | `/images` | Preparar ou confirmar geração de imagem |
| `POST` | `/videos` | Preparar ou confirmar geração de vídeo |
| `POST` | `/images/upscale` | Preparar ou confirmar upscale de imagem |
| `POST` | `/videos/upscale` | Preparar ou confirmar upscale de vídeo |
| `POST` | `/uploads` | Preparar ou confirmar upload |
| `GET` | `/jobs/{job_id}` | Consultar ou atualizar job |
| `POST` | `/jobs/{job_id}/download` | Salvar resultado na máquina do servidor |

### Exemplo: prévia de imagem

Após aprovar o pareamento e selecionar a aba, envie `POST /images` com os identificadores reais da conexão e do projeto:

```json
{
  "connection_id": "<connection_id>",
  "project_id": "<project_id>",
  "input": {
    "prompt": "Um cubo vermelho sobre uma mesa de madeira, luz natural",
    "model": "nano_banana_2",
    "ratio": "1:1",
    "references": []
  },
  "confirm": false
}
```

Depois de conferir a prévia e obter aprovação humana, reenvie o mesmo corpo com `confirm` definido como `true` e o campo `preview_id` preenchido com o identificador da prévia retornada. Não altere os dados da operação entre prévia e confirmação.

Para atualizar o job, use `GET /jobs/{job_id}` com os parâmetros de consulta `connection_id`, `project_id` e `refresh=true`. Os schemas completos estão na documentação OpenAPI local.

## Segurança e créditos

- Mantenha MCP e REST locais sempre que possível. O pareamento da extensão não substitui autenticação de acesso ao servidor HTTP.
- A API REST atual não implementa autenticação HTTP própria e pode ler arquivos locais para upload e gravar downloads. Trate o acesso a ela como acesso privilegiado à máquina.
- Confira a conta, a aba selecionada e a prévia antes de confirmar operações.
- Uma prévia não representa autorização para executar. Clientes e agentes devem solicitar aprovação humana antes da confirmação.
- Consulte os custos e a disponibilidade na interface do Flow; estimativas documentadas podem ficar desatualizadas.
- Não compartilhe cookies, tokens, segredos de pareamento, bancos de jobs ou dados privados em issues e logs.
- Respeite os termos do Google Flow e os direitos sobre conteúdos enviados e gerados. A licença do código não concede direitos sobre serviços ou resultados de terceiros.

## Compatibilidade e limitações

O projeto utiliza chamadas internas do Flow no contexto do navegador, não uma API pública estável de geração. Mudanças no serviço, no reCAPTCHA, nos modelos ou nos planos podem interromper operações.

- Os cenários registrados na matriz foram verificados em **4 e 5 de outubro de 2026**; não são testes contínuos de disponibilidade.
- `veo_lite_low_priority` e `veo_fast_ultra` estão documentados como não implementados.
- Upscale de imagem em 4K não está validado como bem-sucedido na conta usada nos registros.
- A extensão está configurada para a ponte local na porta `9233`. Alterar apenas a porta do servidor não reconfigura a extensão.
- Jobs interrompidos podem exigir verificação manual antes de qualquer nova submissão.

## Desenvolvimento

### Estrutura

```text
openflow/
├── src/flow_mcp/       Servidores, ponte, operações e persistência
│   ├── server.py      Entrada MCP
│   ├── api.py         Entrada REST
│   ├── service.py     Operações compartilhadas
│   ├── bridge.py      Ponte WebSocket
│   ├── manager.py     Conexões e seleção de contexto
│   ├── pairing.py     Pareamento da extensão
│   └── jobs.py        Persistência dos jobs
├── extension/         Extensão Chrome Manifest V3
│   └── tests/         Testes JavaScript
├── tests/             Testes Python
├── docs/              Verificações e diagnósticos técnicos
├── pyproject.toml     Dependências e ferramentas de qualidade
└── LICENSE            Licença MIT original
```

### Verificações locais

Instale as dependências com `uv sync --extra dev` e execute, na raiz:

```bash
uv run pytest
uv run ruff check .
uv run mypy
node --test extension/tests/*.test.mjs
```

A suíte cobre contratos, pareamento, operações, persistência e integração com componentes simulados. Ela não substitui verificações reais na conta do Flow, que podem consumir créditos e devem ser executadas apenas com autorização.

## Solução de problemas

| Sintoma | O que verificar |
| --- | --- |
| Extensão não conecta | Servidor ativo, conexão habilitada no popup e porta `9233` disponível |
| Porta já em uso | Outro processo MCP ou REST pode estar executando a mesma ponte |
| Pareamento pendente | Compare o código da extensão antes de aprovar a solicitação |
| Aba não disponível | Abra o Flow autenticado, consulte a conexão e selecione a aba novamente |
| Falha após atualizar a extensão | Recarregue a aba do Flow para executar os scripts da versão atual |
| `submitted_unverified` | Verifique o job e o Flow antes de qualquer reenvio |
| `rpc_rejected` | Confira modelo, entradas, plano e restrições na matriz de verificações |
| `native_recaptcha_automation_unsupported` | A integração de reCAPTCHA esperada não está disponível; recarregue a aba e verifique a compatibilidade |

## Contribuições

Contribuições de código, testes e documentação são bem-vindas.

1. Descreva o problema ou a mudança proposta, incluindo passos de reprodução quando aplicável.
2. Mantenha as alterações focadas e siga os padrões existentes em Python e JavaScript.
3. Adicione ou ajuste testes quando mudar comportamento.
4. Execute as verificações locais antes de enviar uma contribuição.
5. Informe quais verificações foram realizadas e se houve testes reais no Flow.

Ao relatar problemas, inclua versões do Python, Chrome e extensão, além de mensagens de erro sanitizadas. Não inclua credenciais, dados de conta ou arquivos de mídia privados.

## Créditos e licença

Este projeto deriva do código de **tuannguyenhoangit-droid**. A autoria original é reconhecida e o aviso de copyright foi mantido sem alterações:

```text
Copyright (c) 2026 tuannguyenhoangit-droid
```

Distribuído sob a [licença MIT](LICENSE), que permite uso, cópia, modificação, distribuição e uso comercial, inclusive venda, desde que sejam preservados os avisos exigidos pela licença. O software é fornecido sem garantias, conforme o texto integral da licença.

Google, Google Flow e os nomes dos modelos pertencem aos respectivos titulares. Sua menção descreve compatibilidade e não implica afiliação.
