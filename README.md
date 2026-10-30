# J.A.R.V.I.S — assistente pessoal de IA para Windows

Assistente pessoal com IA que conversa por texto e voz, lembra de preferências,
executa tarefas reais no Windows e mostra cada ação na interface. O backend é
FastAPI + SQLite; a interface é React + TypeScript, aberta em uma janela nativa
(WebView2) ou no navegador.

> **Princípio de segurança:** o modelo de IA nunca executa código arbitrário.
> Ele só pode chamar ferramentas registradas, validadas por JSON Schema e
> avaliadas pela política de permissões em três níveis. Ações críticas sempre
> pedem confirmação explícita.

---

## Índice

- [Recursos](#recursos)
- [Requisitos](#requisitos)
- [Instalação rápida](#instalação-rápida)
- [Executar](#executar)
- [Provedores de IA](#provedores-de-ia)
- [Voz](#voz)
- [Permissões e segurança](#permissões-e-segurança)
- [Ferramentas disponíveis](#ferramentas-disponíveis)
- [Interface](#interface)
- [API local](#api-local)
- [Testes](#testes)
- [Gerar o executável](#gerar-o-executável)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Solução de problemas](#solução-de-problemas)
- [Limitações e cuidados](#limitações-e-cuidados)
- [Licença](#licença)

---

## Recursos

- **Chat com ferramentas reais** — arquivos, aplicativos, terminal, processos,
  volume/mídia, navegador, screenshot, mouse/teclado, janelas.
- **Memória persistente e temporária** em SQLite, pesquisável e editável pela
  interface. O agente pode salvar e consultar memórias durante a conversa.
- **Planejamento visível** — tarefas complexas viram um plano com etapas e
  progresso, persistido na conversa.
- **Voz pt-BR** — palavra-chave “JARVIS”, push-to-talk, STT Google ou Whisper
  local, TTS SAPI ou Edge, interrupção da fala e confirmação por voz opcional.
- **Provedores configuráveis** — DeepSeek, OpenAI, Anthropic, Ollama local e
  qualquer API compatível com OpenAI.
- **Chaves protegidas** — variáveis de ambiente ou cofre DPAPI do Windows
  (`data/secrets.json`), sem texto puro em disco.
- **Interface escura/futurista** com chat, histórico, painel de sistema, plano,
  ações, memória e configurações.
- **Aplicativo desktop** com pywebview/WebView2 e fallback automático para o
  navegador.
- **Testes automatizados** de banco, permissões, caminhos, ferramentas, agente,
  API, voz e cofre de segredos.

---

## Requisitos

| Componente | Versão | Observação |
|---|---|---|
| Windows | 10 ou 11, 64 bits | Necessário para automação, DPAPI e SAPI |
| Python | 3.11+ (recomendado 3.12) | Marcado “Add to PATH” na instalação |
| Node.js | 20+ | Apenas para compilar o frontend / desenvolver |
| WebView2 Runtime | Evergreen | Já vem no Windows 11; no Windows 10 pode ser instalado |
| Microfone e alto-falantes | opcionais | Necessários para os recursos de voz |
| Ollama | opcional | Para modelos locais, sem chave de API |

O WebView2 Evergreen pode ser baixado em
<https://developer.microsoft.com/microsoft-edge/webview2/>. Sem ele, o JARVIS
abre automaticamente no navegador padrão.

---

## Instalação rápida

No PowerShell, na raiz do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

O script:

1. cria o ambiente virtual `.venv`;
2. instala `requirements-dev.txt`;
3. cria `.env` a partir de `.env.example` (se ainda não existir);
4. instala as dependências do frontend e executa `npm run build`;
5. verifica as dependências principais.

Depois, configure uma chave de API no `.env` **ou** pela interface, em
**Config → Chaves de API**.

### Instalação manual

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env

cd frontend
npm install
npm run build
cd ..
```

Para STT local com Whisper, instale o pacote opcional:

```powershell
.\.venv\Scripts\python.exe -m pip install faster-whisper
```

---

## Executar

### Janela desktop (recomendado)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run.ps1
```

ou diretamente:

```powershell
.\.venv\Scripts\python.exe run_jarvis.py
```

O servidor sobe em `http://127.0.0.1:8765`, a janela nativa abre e, ao fechá-la,
o servidor é encerrado com segurança.

### Opções do inicializador

```text
--host ENDEREÇO       Endereço do servidor (padrão: 127.0.0.1)
--port PORTA          Porta (padrão: 8765)
--data-dir CAMINHO    Diretório de dados
--browser             Abre no navegador em vez da janela nativa
--server-only         Sobe apenas o servidor, sem interface
--debug               Ativa o modo de depuração da janela
```

Exemplos:

```powershell
# Navegador
.\.venv\Scripts\python.exe run_jarvis.py --browser

# Servidor em outra porta
.\.venv\Scripts\python.exe run_jarvis.py --port 9000

# Somente API (para integrações ou testes)
.\.venv\Scripts\python.exe run_jarvis.py --server-only
```

Se uma instância saudável já estiver rodando na porta, o launcher reutiliza o
servidor existente em vez de iniciar outro.

### Parâmetros de `scripts\run.ps1`

| Parâmetro | Efeito |
|---|---|
| `-Browser` | Abre no navegador em vez da janela nativa |
| `-ServerOnly` | Sobe apenas o servidor, sem interface |
| `-DebugWindow` | Ativa a depuração da janela WebView2 |
| `-HostAddress 0.0.0.0` | Define o endereço do servidor |
| `-Port 9000` | Define a porta do servidor |

Exemplo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run.ps1 -ServerOnly -Port 9000
```

### Desenvolvimento (hot reload)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

- Backend: <http://127.0.0.1:8765> com `--reload`
- Frontend: <http://127.0.0.1:5173> com proxy para `/api` e `/ws`

Também é possível rodar separadamente:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8765
cd frontend; npm run dev
```

---

## Provedores de IA

Configure em **Config → Modelo e provedor**. A chave pode vir do `.env` ou ser
digitada na interface (cofre DPAPI). Variáveis de ambiente têm precedência.

| Provedor | Variável da chave | Endpoint padrão | Modelo sugerido |
|---|---|---|---|
| DeepSeek | `DEEPSEEK_API_KEY` | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `OPENAI_API_KEY` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Anthropic | `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1` | `claude-3-5-sonnet-latest` |
| Ollama (local) | — | `http://127.0.0.1:11434` | `llama3.1`, `qwen2.5` etc. |
| OpenAI-compatível | `JARVIS_CUSTOM_API_KEY` | `JARVIS_CUSTOM_BASE_URL` | conforme o serviço |

### Exemplo de `.env`

```dotenv
JARVIS_HOST=127.0.0.1
JARVIS_PORT=8765
JARVIS_DEFAULT_PROVIDER=deepseek
JARVIS_DEFAULT_MODEL=deepseek-chat

DEEPSEEK_API_KEY=sk-...
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...

# Ollama local
JARVIS_OLLAMA_BASE_URL=http://127.0.0.1:11434
JARVIS_OLLAMA_NUM_CTX=8192

# API compatível com OpenAI
# JARVIS_CUSTOM_BASE_URL=http://127.0.0.1:8000/v1
# JARVIS_CUSTOM_API_KEY=...
```

Na interface você pode **Testar conexão** e **Listar modelos** para conferir a
configuração antes de conversar.

### Ollama local (grátis, sem chave)

Para rodar um modelo na sua própria máquina:

```powershell
winget install --id Ollama.Ollama -e
ollama pull llama3.1:8b
```

Depois, em **Config → Modelo e provedor**, escolha **Ollama (local)** e o modelo
`llama3.1:8b`. O `.env` também pode definir:

```dotenv
JARVIS_DEFAULT_PROVIDER=ollama
JARVIS_DEFAULT_MODEL=llama3.1:8b
JARVIS_OLLAMA_BASE_URL=http://127.0.0.1:11434
JARVIS_OLLAMA_NUM_CTX=8192
```

- `JARVIS_OLLAMA_NUM_CTX` controla o contexto em tokens (2.048–32.768). O
  padrão de 8.192 comporta as 31 ferramentas e conversas normais.
- Em placas com pouca VRAM, reduza para `4096` ou `6144`.
- O Ollama precisa estar em execução (`ollama serve` ou o app Ollama aberto).
- Modelos locais pequenos podem errar chamadas; o JARVIS normaliza tipos
  simples (por exemplo, `"false"` → `false`) antes de validar a ferramenta.

### Chaves no cofre DPAPI

- As chaves digitadas na interface são cifradas com `CryptProtectData` da conta
  Windows atual e gravadas em `data/secrets.json`.
- O arquivo não é reutilizável em outra conta ou máquina.
- A interface nunca exibe a chave de volta; mostra apenas a origem
  (“via .env”, “no cofre”, “ausente”).
- Remover a chave pelo botão **Remover** apaga o blob do cofre.

> Nunca coloque chaves em arquivos versionados. O `.gitignore` já bloqueia
> `.env`, `data/`, `*.db` e `secrets.json`.

---

## Voz

A voz é opcional e configurável em **Config → Voz e escuta** e
**Config → Síntese de voz**.

### Entrada (STT)

- **Palavra-chave** — diga “Jarvis, abra o navegador”. O microfone só é aberto
  quando você clica no botão de escuta; há um indicador visível enquanto ele
  está ativo.
- **Push-to-talk** — clique no microfone do chat para capturar uma frase única,
  sem palavra-chave.
- **Escuta contínua** — reabre o microfone após cada resposta. O microfone é
  pausado durante o processamento e a fala para evitar realimentação.
- **Motores** — Google (online, sem instalação extra) ou Whisper local
  (`faster-whisper`, offline).
- **Microfone** — escolha o dispositivo padrão ou um índice específico.
- **Idioma** — `pt-BR` por padrão.

### Saída (TTS)

- **SAPI (Windows)** — offline, usa as vozes instaladas no sistema.
- **Edge TTS** — online, vozes neurais pt-BR (Francisca, Antônio, Thalita,
  Brenda, Donato).
- Velocidade, volume e voz configuráveis.
- Respostas a comandos falados são sintetizadas automaticamente por padrão;
  respostas do chat podem ser faladas se você ativar a opção.
- O botão **Parar** interrompe a fala imediatamente.

### Confirmação por voz

Quando `voice_confirm_actions` está ativo, ações pendentes podem ser aprovadas
ou recusadas falando “sim”, “pode executar”, “não”, “cancelar” etc. O
reconhecimento é estrito: frases ambíguas não aprovam nada.

---

## Permissões e segurança

### Três níveis

| Nível | Comportamento | Exemplos |
|---|---|---|
| **1 — Leitura** | Executa automaticamente | listar/ler arquivos, informações do sistema, screenshot, abrir URL, pesquisar memória |
| **2 — Modificação** | Pede confirmação por padrão; pode ser liberado em Config | criar/editar/mover/copiar arquivos, abrir/fechar apps, automação de mouse/teclado, terminal de escrita |
| **3 — Crítico** | **Sempre** pede confirmação explícita; pode ser totalmente desativado | excluir arquivos, encerrar processos, comandos de terminal críticos |

- O nível 2 é configurável com **Confirmar ações de nível 2**.
- O nível 3 nunca executa sem aprovação, mesmo com o nível 2 liberado. Se
  **Permitir ações de nível 3** estiver desligado, a ação é bloqueada.
- A confirmação pausa o loop do agente; a ação fica pendente e persistida até
  você aprovar ou recusar. O histórico continua válido para o provedor.
- Cada execução vira um registro em **Ações**, com argumentos, resultado, erro,
  duração e nível de permissão.

### Proteções de caminho

- O JARVIS só acessa arquivos dentro dos **diretórios autorizados**.
- Não é possível mover, copiar ou apagar a raiz de um diretório autorizado.
- Arquivos sensíveis são bloqueados mesmo dentro das raízes: `.env`, `.ssh`,
  `.aws`, `.gnupg`, `.kube`, `id_rsa`, `secrets.json`, `jarvis.db`,
  `Login Data`, `Cookies`, `key4.db`, `logins.json`, `.pfx`, `.kdbx`, `.key` etc.
- Caminhos são resolvidos com `Path.resolve()`, impedindo traversal (`..`).

### Terminal

- Comandos são classificados em leitura (1), escrita (2) e crítico (3).
- Bloqueios absolutos: formatação de disco, `diskpart`, `bcdedit`, remoção de
  `C:\Windows` ou da raiz da unidade, desativação de Defender/firewall, exclusão
  de backups/sombras, `reg delete HKLM`.
- Comandos que citam arquivos sensíveis são recusados.
- Timeout configurável, saída truncada e árvore de processos encerrada em caso
  de timeout.

### Outras proteções

- O servidor escuta apenas em `127.0.0.1` por padrão.
- Não há execução arbitrária de código pelo modelo: só ferramentas registradas,
  com JSON Schema `additionalProperties: false`.
- Memórias que parecem conter senhas, tokens ou chaves são recusadas.
- Logs não incluem chaves de API.
- O executável **não** roda como administrador.

> **Aviso:** as permissões são guardrails de software, não uma sandbox de
> sistema operacional. Execute o JARVIS com uma conta de usuário comum e revise
> as ações de nível 2/3 antes de aprovar.

---

## Ferramentas disponíveis

31 ferramentas registradas, agrupadas por categoria:

### Arquivos (11)

| Ferramenta | Nível | Descrição |
|---|---|---|
| `search_files` | 1 | Pesquisa arquivos por nome |
| `list_directory` | 1 | Lista arquivos e subpastas |
| `read_file` | 1 | Lê arquivo de texto |
| `get_file_info` | 1 | Metadados de arquivo/pasta |
| `create_file` | 2 | Cria arquivo de texto |
| `edit_file` | 2 | Substitui texto exato |
| `create_directory` | 2 | Cria pasta |
| `move_file` | 2 | Move/renomeia |
| `copy_file` | 2 | Copia |
| `organize_folder` | 2 | Organiza por tipo (com dry-run) |
| `delete_file` | 3 | Envia para a Lixeira ou apaga |

### Aplicativos e janelas (4)

| Ferramenta | Nível | Descrição |
|---|---|---|
| `open_application` | 1 | Abre app por nome conhecido |
| `open_path` | 1 | Abre pasta/arquivo no app padrão |
| `manage_windows` | 1 | Lista, foca, minimiza, maximiza, fecha janelas |
| `close_application` | 2 | Encerra app por processo/PID |

### Sistema e mídia (5)

| Ferramenta | Nível | Descrição |
|---|---|---|
| `get_system_information` | 1 | Informações reais do Windows |
| `get_resource_usage` | 1 | CPU, RAM, disco, rede, GPU, bateria |
| `get_process_list` | 1 | Processos em execução |
| `control_volume` | 1 | Volume master |
| `control_media` | 1 | Play/pause, faixa, parar |

### Terminal (1)

| Ferramenta | Nível | Descrição |
|---|---|---|
| `execute_terminal_command` | 1–3 | PowerShell/CMD com classificação de risco |

### Navegador (3)

| Ferramenta | Nível | Descrição |
|---|---|---|
| `browser_search` | 1 | Pesquisa no navegador padrão |
| `open_url` | 1 | Abre URL http/https |
| `browser_automation` | 2 | Abre URL, nova aba, digita, clica, rola |

### Automação (2)

| Ferramenta | Nível | Descrição |
|---|---|---|
| `screenshot` | 1 | Captura a tela em PNG |
| `computer_interaction` | 2 | Move/clica/arrasta/rola/digita |

### Memória (4)

| Ferramenta | Nível | Descrição |
|---|---|---|
| `save_memory` | 1 | Salva preferência/fato/projeto |
| `search_memory` | 1 | Busca memórias |
| `list_memories` | 1 | Lista memórias |
| `delete_memory` | 2 | Exclui memória por ID |

### Planejamento (1)

| Ferramenta | Nível | Descrição |
|---|---|---|
| `update_plan` | 1 | Cria/atualiza o plano visível |

---

## Interface

- **Chat** — mensagens com Markdown, chamadas de ferramenta, confirmações e
  botão de cancelamento.
- **Histórico** — criar, selecionar e excluir conversas; título automático.
- **Sistema** — CPU, RAM, disco, rede, GPU, bateria, banco, provedor e
  ferramentas.
- **Plano** — progresso e etapas da tarefa atual.
- **Ações** — histórico filtrável, detalhes de argumentos/resultado e aprovação
  de pendências.
- **Memória** — busca, criação, edição, alternância persistente/temporária e
  exclusão.
- **Config** — provedor, modelo, parâmetros, chaves, permissões, raízes
  autorizadas, terminal, voz, TTS, memória e instruções extras.
- **Orbe de estado** — muda de cor para ocioso, ouvindo, pensando, executando,
  falando e erro.

---

## API local

A documentação interativa fica em <http://127.0.0.1:8765/docs>.

### Principais rotas

| Método | Rota | Função |
|---|---|---|
| `GET` | `/api/health` | Saúde do servidor e do banco |
| `GET` | `/api/status` | Estado, recursos, provedor, voz, ferramentas |
| `GET` | `/api/tools` | Lista as 31 ferramentas |
| `GET` | `/api/providers` | Provedores e origem das chaves |
| `POST` | `/api/providers/{id}/test` | Testa conexão |
| `GET` | `/api/providers/{id}/models` | Lista modelos |
| `PUT` | `/api/providers/{id}/key` | Salva chave no cofre DPAPI |
| `DELETE` | `/api/providers/{id}/key` | Remove chave do cofre |
| `GET` | `/api/settings` | Preferências atuais |
| `PUT` | `/api/settings` | Atualiza `{ "values": { ... } }` |
| `POST` | `/api/settings/reset` | Restaura padrões |
| `GET` | `/api/conversations` | Lista conversas |
| `POST` | `/api/conversations` | Cria conversa |
| `GET` | `/api/conversations/{id}` | Detalhe + mensagens + plano + ações |
| `PATCH` | `/api/conversations/{id}` | Renomeia/arquiva |
| `DELETE` | `/api/conversations/{id}` | Exclui conversa |
| `GET` | `/api/conversations/{id}/messages` | Mensagens |
| `POST` | `/api/chat` | Envia mensagem |
| `POST` | `/api/actions/{id}/approve` | Aprova ação pendente |
| `POST` | `/api/actions/{id}/deny` | Recusa ação pendente |
| `GET` | `/api/actions` | Histórico de ações |
| `GET` | `/api/actions/pending` | Ações pendentes |
| `POST` | `/api/cancel` | Cancela execução |
| `GET` | `/api/conversations/{id}/plan` | Plano da conversa |
| `PUT` | `/api/conversations/{id}/plan` | Atualiza plano |
| `GET` | `/api/memories` | Lista memórias |
| `GET` | `/api/memories/search?q=` | Busca memórias |
| `POST` | `/api/memories` | Cria memória |
| `PATCH` | `/api/memories/{id}` | Atualiza memória |
| `DELETE` | `/api/memories/{id}` | Exclui memória |
| `GET` | `/api/voice/status` | Estado da voz |
| `GET` | `/api/voice/microphones` | Lista microfones |
| `POST` | `/api/voice/start` | Ativa palavra-chave |
| `POST` | `/api/voice/stop` | Desliga microfone |
| `POST` | `/api/voice/listen` | Push-to-talk |
| `POST` | `/api/voice/speak` | Sintetiza texto |
| `POST` | `/api/voice/stop-speaking` | Interrompe fala |
| `WS` | `/ws` | Eventos em tempo real |

### Eventos WebSocket

`hello`, `runtime.state`, `voice.started`, `voice.listening`, `voice.stopped`,
`voice.command`, `voice.error`, `voice.confirmation`, `message.created`,
`conversation.updated`, `conversation.deleted`, `plan.updated`,
`confirmation.required`, `tool.started`, `tool.finished`, `action.blocked`,
`assistant.error`, `settings.updated`, `providers.updated`, `memory.*`.

Exemplo de mensagem de chat:

```json
{
  "message": "Organize minha pasta Downloads",
  "conversation_id": null,
  "source": "text",
  "speak": false
}
```

---

## Testes

```powershell
# Suíte completa
.\.venv\Scripts\python.exe -m pytest tests -q

# Lint
.\.venv\Scripts\ruff.exe check backend tests desktop run_jarvis.py scripts\make_icon.py

# Tudo (lint + testes + build do frontend)
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

Cobertura atual: **112 testes**, incluindo:

- migrações, repositórios e configurações;
- permissões nos três níveis e bloqueios;
- isolamento de caminhos e arquivos sensíveis;
- ferramentas de arquivos (criação, edição, busca, organização, exclusão);
- loop do agente, tool calling, confirmações, cancelamento e sanitização do
  histórico;
- API REST e WebSocket (incluindo fluxo de aprovação);
- memória, heurística de segredos e utilitários;
- palavra-chave, limpeza de texto para fala e confirmação por voz;
- cofre DPAPI e precedência de chaves de ambiente.

Os testes usam um provedor falso determinístico; nenhuma chamada real de IA é
feita.

---

## Gerar o executável

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

O script executa lint, testes, build do frontend, gera o ícone e roda o
PyInstaller com `jarvis.spec`.

Saída:

```text
dist\JARVIS\JARVIS.exe
```

- Distribuição **one-dir**: mantenha a pasta `dist\JARVIS` inteira.
- Dados do usuário: `%LOCALAPPDATA%\JARVIS` (banco, logs, screenshots, cofre).
- `.env` opcional ao lado do `JARVIS.exe`.
- O WebView2 Runtime é necessário para a janela nativa; sem ele, abre no
  navegador.

Para pular etapas durante o desenvolvimento:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -SkipTests -SkipFrontend
```

---

## Estrutura do projeto

```text
jarvis/
├── backend/
│   ├── ai/               # provedores e tipos normalizados
│   ├── api/              # rotas REST, WebSocket e schemas
│   ├── config/           # AppSettings e RuntimeSettings
│   ├── core/             # agente, assistente, memória, plano, permissões
│   ├── database/         # SQLite, migrações, modelos e repositórios
│   ├── security/         # cofre DPAPI
│   ├── tools/            # 31 ferramentas + registry + path guard
│   ├── voice/            # STT, TTS, wake word e orquestração
│   ├── container.py      # composition root
│   └── main.py           # fábrica FastAPI
├── desktop/              # janela pywebview/WebView2 e fallback
├── frontend/
│   ├── src/              # React + TypeScript
│   └── dist/             # build servido pelo FastAPI
├── tests/                # 112 testes
├── scripts/              # install, run, dev, test, build, ícone
├── assets/               # ícone do aplicativo
├── data/                 # banco, logs, screenshots e cofre (não versionado)
├── run_jarvis.py         # inicializador do app desktop
├── jarvis.spec           # especificação PyInstaller
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

---

## Solução de problemas

### “Frontend não compilado”

Execute:

```powershell
cd frontend
npm install
npm run build
```

### A janela nativa não abre

- Verifique se o **WebView2 Evergreen Runtime** está instalado.
- Rode com `--browser` para confirmar que o backend está saudável.
- Veja `data\logs\jarvis.log`.

### Microfone não encontrado

- Confira as permissões de microfone em **Configurações do Windows → Privacidade
  e segurança → Microfone**.
- Teste outro dispositivo em **Config → Voz e escuta → Microfone**.
- Se o PyAudio falhar ao instalar, use Python 3.12 64 bits e reinstale
  `pip install PyAudio`.

### Voz não reconhece “Jarvis”

- O motor Google exige internet; para uso offline, instale `faster-whisper` e
  selecione Whisper.
- Ajuste a palavra-chave em Config; o reconhecimento tolera acentos e pequenos
  erros, mas não frases muito distantes.
- Verifique se o microfone correto está selecionado e se o indicador de escuta
  está ativo.

### Erro 401/403 do provedor

- Confira a chave e o modelo em **Config**.
- Use **Testar conexão**.
- Para Ollama, confirme que `ollama serve` está rodando e que o modelo foi
  baixado (`ollama pull llama3.1`).

### Porta 8765 em uso

```powershell
.\.venv\Scripts\python.exe run_jarvis.py --port 9000
```

Se for outra instância do JARVIS, o launcher a reutiliza automaticamente.

### Ação bloqueada

- Nível 3 desativado: ative **Permitir ações de nível 3** e aprove a ação.
- Caminho fora das raízes: adicione o diretório em **Config → Diretórios
  autorizados**.
- Arquivo sensível: a proteção é intencional; opere manualmente.
- Comando proibido: a política de terminal bloqueia operações catastróficas.

### Antivírus sinaliza o executável

Executáveis PyInstaller às vezes geram falso positivo. **Não desative o
antivírus.** Prefira rodar pelo Python, assinar o executável ou adicionar uma
exclusão consciente para a pasta `dist\JARVIS`.

### Onde ficam os dados?

- Desenvolvimento: `./data/`
- Executável: `%LOCALAPPDATA%\JARVIS\`
- Banco: `jarvis.db`; logs: `logs\jarvis.log`; cofre: `secrets.json`;
  screenshots: `screenshots\`.

---

## Limitações e cuidados

- O JARVIS foi feito para uso **local e pessoal**. Não exponha a porta na
  internet: não há autenticação de usuários.
- As permissões reduzem riscos, mas não substituem backup e bom senso. Revise
  ações de nível 2/3.
- A automação de mouse/teclado e navegador depende do layout da tela e pode
  falhar se a janela mudar.
- O modelo de IA pode cometer erros; confirme informações importantes.
- O STT Google envia áudio para a Google. Use Whisper local se precisar de
  privacidade total.
- O Edge TTS envia o texto para os serviços da Microsoft.
- O screenshot captura a tela inteira, incluindo conteúdo sensível visível;
  revise antes de compartilhar.
- O projeto não é afiliado à Marvel/Disney; “JARVIS” é usado como referência
  cultural.

---

## Licença

MIT. Consulte `pyproject.toml`.
