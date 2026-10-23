# pyDoSap

Cliente desktop (PySide6, tema escuro) para lançar CT-es no SAP: busca os CT-es na
API `escrituracao-ctes`, lança **pedido de frete + MIRO** ou **CT-e de custo**
(NP01 + MIRO + fornecimento de ordem de venda) via SAP GUI Scripting, grava o log
no BigQuery e permite editar as configurações de lançamento. Substitui os clientes
Excel/VBA `SAP_GUI_BOT_ESCRITURACAO_CTES.xlsm` e `ESCRITURACAO_CTES_CUSTO.xlsm`;
o backend Flask continua o mesmo.

## Abas

- **Lançamento** — CT-e de frete: busca em lote, ME21N (pedido) + MIRO; filtro
  "Somente validados" ativo por padrão; colunas em ordem e largura fixas
  (`pydosap/cte_columns.py`); "Visualização compacta" (linhas mais baixas) e
  "Exportar para Excel" (respeita ordem/visibilidade das colunas e o filtro/
  ordenação da tabela no momento do clique)
- **CT-e de Custo** — busca por chave, simula/lança cada NF (NP01), MIRO do CT-e,
  fornece as ordens de venda casadas (VA02)
- **Configurações** — 4 sub-abas (`config_lancamento`, `config_cte_custo`,
  `config_filiais`, `regioes_csc`), cada uma lida e gravada via API
  (`GET/POST /cte/config/<ação>/<tabela>`). "Salvar" grava a tabela inteira
  (o backend substitui a tabela, não faz update por linha); "Reverter"
  restaura o backup feito automaticamente na última gravação.
- **Upload de XML** — envia XMLs de CT-e para o TMS, um por vez (upload síncrono: a resposta
  já diz se o Lincros integrou o documento — só vale como integrado se vier o `oidCte`).
  A opção **Forçar integração** (`POST /cte/forcar-integracao`) serve para CT-es com mais de
  90 dias, que a listagem do Lincros não traz: o backend sobe o XML, recupera o oid e grava a
  linha direto em `ctes_api`; o CT-e passa a aparecer na aba Lançamento (a resposta informa se
  ele ficou "PARA LANCAR" ou o motivo do bloqueio). Reenviar o mesmo XML é seguro (não duplica).

## Executar (Windows, com SAP GUI aberto e logado)

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      :: preencha PYDOSAP_API_TOKEN
python main.py
```

Pré-requisitos do SAP: scripting habilitado no cliente (Opções do SAP GUI) e no
servidor (`sapgui/user_scripting`). O BigQuery é acessado apenas pelo backend
(API); o cliente não precisa de credenciais do Google Cloud.

## Estrutura

```
main.py                     ponto de entrada
pydosap/
  config.py                 .env / URL+token da API
  models.py                 Resp, FiltroCTE, ControleLancamento, tipos do CT-e de custo
  formatting.py             formatos SAP (vírgula decimal, dd.MM.yyyy, sinal à direita,
                             referência NF, conversão de tipo p/ edição de tabela,
                             data_br/moeda_brl para exibição em tela e no Excel)
  cte_columns.py             ordem/rótulo/largura/alinhamento das colunas do CT-e de
                             despesa (sem Qt — usado pelo modelo da tabela e pela exportação)
  api_client.py             HTTP (= cRequests.cls); rotas de CT-e, config (buscar/
                             atualizar/reverter por tabela) e log
  sap/session.py            SAP GUI Scripting genérico (= SAP.bas / clsSAPAutomation)
  sap/pedido.py             ME21N, CT-e de frete (= CRIAR_PEDIDO.bas)
  sap/fatura.py             MIRO, CT-e de frete (= LANCAR_FATURA.bas do frete)
  sap/custo.py               NP01 + MIRO + venda casada, CT-e de custo
                             (= LANCAR_NOTAS.bas, LANCAR_FATURA.bas e
                             FORNECER_ORDENS.bas do projeto CUSTO)
  services/lancamento.py    fluxo do lote de frete (= LancarCTEs do MAIN.bas)
  services/custo.py          fluxo de um CT-e de custo (= LancarCteCusto do MAIN_CUSTO.bas)
  services/upload.py        upload de XML (= CTE_UPLOAD.bas)
  services/exportacao.py    exporta a tabela de CT-es de despesa para .xlsx (openpyxl)
  ui/                       telas PySide6 (sem regra de negócio), tema em ui/styles.py,
                             ícone/logo em ui/assets/
tests/                      unittest, com SAP e API falsos (rodam em qualquer SO,
                             sem SAP GUI nem credenciais reais)
```

## Testes

```bash
python -m unittest discover -s tests -t .
```

## Executável

```bat
pip install pyinstaller
pyinstaller --noconfirm --windowed --name pyDoSap --icon pydosap\ui\assets\icon.ico ^
    --add-data "pydosap\ui\assets;pydosap/ui/assets" main.py
```
Coloque o `.env` ao lado do `.exe` (ou em `%APPDATA%\pyDoSap\.env`).

## Observações sobre o porte do VBA

Correções aplicadas em relação ao VBA original (documentadas para revisão):

- **ME21N (frete):** o `InStr` do erro de material estava com os argumentos
  invertidos e quase nunca disparava.
- **MIRO (frete):** a data de lançamento informada pelo usuário nunca era
  aplicada (variável de controle não era atribuída); agora é.
- **MIRO (frete):** o VBA nunca marcava sucesso na fatura; aqui marca quando o
  número do documento é identificado na mensagem do SAP.
- **Log (frete):** grava a mensagem consolidada (pedido + MIRO) mesmo quando só
  o pedido falhou; CT-es não marcados não geram mais um log vazio.
- **FORNECER_ORDENS (custo):** ao pular uma ordem "Carga para estoque", a
  variável de mensagem/remessa não era resetada e podia herdar o resultado da
  ordem anterior. Corrigido.
- **LancarCteCusto (custo):** em caso de falha ao simular ou lançar uma NF, a
  mensagem de erro real chegava a se perder na tela final (variável errada /
  não atribuída); aqui a mensagem do passo que falhou é sempre propagada.
- **Log do CT-e de custo:** o fluxo original não gravava log nenhum. Agora
  todo lançamento (custo ou frete/despesa) grava, sempre, em `sapguibot_ctes.log`,
  incluindo `tipo_lancamento` (`'CUSTO'`/`'DESPESA'`) e `mandante`
  (`GuiSessionInfo.Client`) — mesmo quando o SAP lança uma exceção inesperada.
- **NP01 (custo):** `S_NFKEY-LOW` e `G_SELFLD_TAB-LOW` agora são preenchidos com
  `fill_text` (GuiTextField), não `fill_ctext` (GuiCTextField), a pedido do usuário.

## Assunções (a confirmar)

Os nomes de campo abaixo, usados na exportação/ordenação da tabela de CT-es de
despesa, foram inferidos do porte do VBA e não têm confirmação de schema:
`numero`, `serie`, `nomeTransportadora` e `miro` apareceram no VBA original;
`valor` foi um palpite (o VBA não expõe esse nome explicitamente na listagem).
Se a API usar outro nome para o valor do CT-e, a coluna não quebra — ela só cai
no grupo "resto" (ordem/largura/formato padrão) até `pydosap/cte_columns.py`
ser ajustado com o nome certo.

Como no lançamento de frete, o fluxo de CT-e de custo (`sap/custo.py`) não foi
validado contra um SAP GUI real — é um porte fiel do VBA, mas os nomes de campo
e a sequência de telas precisam ser conferidos com um CT-e de teste antes de
usar em produção.
