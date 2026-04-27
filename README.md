# SIT_Conecta

Automação e painel visual para acompanhamento dos cenários do **SIT Conecta**.

Este repositório tem dois blocos principais:

- **Automação em Python + Playwright** para acessar o GTN, baixar relatórios CSV e consolidar os arquivos em um único resultado.
- **Dashboard web estático** para leitura do CSV consolidado e exibição de indicadores, ranking e visão gerencial da execução dos cenários.

## O que este projeto faz

A automação:

- abre o GTN
- realiza login com credenciais via `.env`
- navega até a área de execução de testes
- baixa múltiplos relatórios CSV
- consolida os arquivos em um único CSV final
- grava logs e arquivos de apoio para depuração

O dashboard:

- lê automaticamente o arquivo `output/Cenarios_Consolidados_atualizado.csv`
- exibe total de cenários, concluídos, em andamento e não iniciados
- mostra ranking de líderes
- mostra áreas com melhor desempenho
- atualiza automaticamente em intervalo configurado no front-end

---

## Estrutura do projeto

```text
SIT_Conecta/
├── SCRIPT_DEFINITIVO.py
├── script_Pontual_GTN_blindado_v6_alterado_v2.py
├── index.html
├── login.html
├── style.css
├── script.js
├── auth.js
├── output/
│   └── Cenarios_Consolidados_atualizado.csv
├── downloads/
├── execucao_fluxo2.log
├── .gitignore
└── README.md
```

### Arquivos principais

- `SCRIPT_DEFINITIVO.py`: script principal de automação e consolidação.
- `script_Pontual_GTN_blindado_v6_alterado_v2.py`: variação do script principal.
- `index.html`: dashboard principal.
- `login.html`: tela de login do dashboard.
- `script.js`: lógica de leitura do CSV e montagem dos indicadores.
- `auth.js`: autenticação simples do dashboard via JavaScript.
- `output/`: saída final da consolidação.
- `downloads/`: arquivos baixados durante a execução.
- `execucao_fluxo2.log`: log de execução da automação.

---

## Pré-requisitos

Antes de começar, tenha instalado na máquina:

- **Python 3.10 ou superior**
- **Google Chrome** ou navegador Chromium compatível
- **Git**
- acesso ao ambiente **GTN**

Também é necessário instalar os navegadores do Playwright após instalar as dependências do Python.

---

## Como clonar o repositório

```bash
git clone <URL_DO_REPOSITORIO>
cd SIT_Conecta
```

---

## Como criar e ativar o ambiente virtual

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Windows CMD

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

---

## Como instalar as dependências

Como o projeto atual não contém um `requirements.txt` fechado, instale primeiro os pacotes-base abaixo:

```bash
pip install playwright python-dotenv
```

Depois, instale os navegadores do Playwright:

```bash
python -m playwright install
```

### Sugestão de `requirements.txt`

Se quiser versionar as dependências do projeto, crie um arquivo `requirements.txt` com:

```txt
playwright
python-dotenv
```

E então instale com:

```bash
pip install -r requirements.txt
python -m playwright install
```

---

## Configuração do arquivo `.env`

O arquivo `.env` **não deve ser enviado ao repositório**, pois contém dados sensíveis.

Crie um arquivo chamado `.env` na raiz do projeto com base no exemplo abaixo:

```env
GTN_URL=https://gtn.ninecon.com.br/ords/r/gtn/gtn/login?tz=-3:00
GTN_HOME_URL=https://gtn.ninecon.com.br/ords/r/gtn/gtn/home
GTN_USER=seu_usuario
GTN_PASS=sua_senha

GTN_DOWNLOAD_TIMEOUT_MS=180000
GTN_DEFAULT_TIMEOUT_MS=60000
GTN_POST_DOWNLOAD_PAUSE_MS=2000
GTN_MAX_TENTATIVAS_DOWNLOAD=3
```

### Variáveis utilizadas

- `GTN_URL`: URL de login do GTN
- `GTN_HOME_URL`: URL da home do GTN
- `GTN_USER`: usuário de acesso
- `GTN_PASS`: senha de acesso
- `GTN_DOWNLOAD_TIMEOUT_MS`: tempo máximo de espera para download
- `GTN_DEFAULT_TIMEOUT_MS`: timeout padrão do Playwright
- `GTN_POST_DOWNLOAD_PAUSE_MS`: pausa após download
- `GTN_MAX_TENTATIVAS_DOWNLOAD`: número máximo de tentativas por download

---

## Como executar a automação

Com o ambiente virtual ativado e o `.env` configurado:

```bash
python SCRIPT_DEFINITIVO.py
```

Ao final da execução, o script deve:

- baixar os relatórios para a pasta `downloads/`
- gerar o consolidado final em `output/`
- registrar o andamento em `execucao_fluxo2.log`

### Saídas esperadas

- `downloads/*.csv`
- `output/Cenarios_Consolidados_atualizado.csv`
- `execucao_fluxo2.log`
- capturas de debug e HTML em caso de erro

---

## Como abrir o dashboard

O dashboard lê o CSV usando `fetch()`. Por isso, o ideal é abrir os arquivos por um servidor local simples, e não apenas dar duplo clique no `index.html`.

Na raiz do projeto, execute:

```bash
python -m http.server 8000
```

Depois acesse no navegador:

```text
http://localhost:8000/login.html
```

Após login, o painel principal será carregado e tentará ler automaticamente:

```text
output/Cenarios_Consolidados_atualizado.csv
```

---

## Fluxo recomendado de uso

1. Configure o `.env`
2. Ative a `.venv`
3. Execute o script Python
4. Confirme se o CSV consolidado foi gerado em `output/`
5. Suba o servidor local com `python -m http.server 8000`
6. Acesse `login.html`
7. Visualize o dashboard em `index.html`

---

## Logs e depuração

O projeto grava log em:

```text
execucao_fluxo2.log
```

Em caso de falha, o script também pode salvar:

- screenshots
- HTML da página no momento do erro

Esses arquivos ajudam a diagnosticar problemas como:

- timeout de download
- mudança de seletor no GTN
- falha de login
- modal inesperado
- estrutura divergente entre CSVs baixados

---

## Segurança

### Arquivos que não devem ir para o Git

O `.gitignore` já protege itens importantes, principalmente:

- `.env`
- `.venv/`
- caches Python
- arquivos temporários

### Atenção importante

Embora o `.env` fique de fora corretamente, o arquivo `auth.js` do dashboard contém autenticação fixa no front-end. Isso significa que, do jeito atual, qualquer pessoa com acesso aos arquivos pode visualizar essas credenciais no navegador.

Para ambiente interno e controlado, isso pode até quebrar um galho. Para qualquer uso mais sério, o ideal é:

- remover credenciais hardcoded do JavaScript
- validar login no back-end
- usar sessão real e controle de acesso do lado do servidor

Sem rodeio: esconder só o `.env` e deixar segredo no `auth.js` não fecha a conta de segurança.

---

## Problemas comuns

### 1. `ModuleNotFoundError`
Instale as dependências:

```bash
pip install playwright python-dotenv
```

### 2. Navegador do Playwright não instalado

```bash
python -m playwright install
```

### 3. O script não encontra usuário ou senha
Verifique se o arquivo `.env` está na raiz do projeto e se contém `GTN_USER` e `GTN_PASS`.

### 4. O dashboard não carrega o CSV
Verifique:

- se o arquivo existe em `output/Cenarios_Consolidados_atualizado.csv`
- se você abriu o projeto via servidor local
- se o CSV tem a coluna `Gerado em`

### 5. Já existe uma execução em andamento
O projeto usa um arquivo de trava (`rodando.lock`) para evitar execução duplicada. Se o processo anterior terminou de forma anormal, remova o arquivo manualmente antes de nova execução.

---

## Melhorias futuras recomendadas

- criar `requirements.txt` oficial no repositório
- adicionar `.env.example`
- mover autenticação do dashboard para back-end
- separar scripts estáveis de scripts experimentais
- versionar melhor os nomes dos scripts
- adicionar tratamento de logs por rotação
- publicar instruções de deploy interno

---

## Exemplo de `.env.example`

Você pode deixar no repositório um arquivo seguro chamado `.env.example`:

```env
GTN_URL=https://gtn.ninecon.com.br/ords/r/gtn/gtn/login?tz=-3:00
GTN_HOME_URL=https://gtn.ninecon.com.br/ords/r/gtn/gtn/home
GTN_USER=
GTN_PASS=
GTN_DOWNLOAD_TIMEOUT_MS=180000
GTN_DEFAULT_TIMEOUT_MS=60000
GTN_POST_DOWNLOAD_PAUSE_MS=2000
GTN_MAX_TENTATIVAS_DOWNLOAD=3
```

---

## Licença

Defina aqui a licença do projeto, caso deseje disponibilizá-lo formalmente.

Exemplo:

```text
Uso interno.
```

---

## Resumo direto

Para rodar sem drama:

```bash
python -m venv .venv
```

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
pip install playwright python-dotenv
python -m playwright install
```

```bash
python SCRIPT_DEFINITIVO.py
```

```bash
python -m http.server 8000
```

Abra:

```text
http://localhost:8000/login.html
```
