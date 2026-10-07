# IFSP — dashboard solar e meteorológica

Flask serve a página e as APIs JSON. O frontend usa JavaScript e Chart.js
(incluído em `dashboard/static/vendor`); SQLAlchemy consulta os dados em
PostgreSQL ou SQLite. A dashboard usa leituras reais da planilha
`23092026_1.xlsx`, sem dados simulados.

## Executar localmente com SQLite

No PowerShell, dentro desta pasta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app import-excel 23092026_1.xlsx
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000
```

Abra <http://127.0.0.1:5000>. Sem `DATABASE_URL`, o banco usado é
`instance/monitoramento.sqlite`. Se houver `.env` apontando para PostgreSQL,
a aplicação usará PostgreSQL. Para forçar SQLite temporariamente:

```powershell
$env:DATABASE_URL = 'sqlite:///instance/monitoramento.sqlite'
```

Nesta sessão, a prévia com as 65.367 leituras foi iniciada na porta **5001**:
<http://127.0.0.1:5001>. Uma captura está em [docs/dashboard.png](docs/dashboard.png).
A interface usa a identidade visual do IFSP, com marca oficial horizontal,
cores institucionais e Open Sans. Veja [a prévia atualizada](docs/dashboard-ifsp.png)
e [as referências de identidade](docs/identidade-ifsp.md).
A conexão PostgreSQL informada em `.env` retornou timeout, inclusive fora
do ambiente restrito; a importação nesse servidor não foi concluída.
O `.env` existente foi preservado. Para repetir a prévia SQLite:

```powershell
$env:DATABASE_URL = 'sqlite:///instance/monitoramento.sqlite'
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5001
```

Não é necessário ativar o ambiente virtual. Os comandos usam diretamente
o executável Python do ambiente. A inicialização não importa dados
automaticamente nem altera tabelas existentes.

## Usar PostgreSQL

Se você já tem um servidor, configure a conexão para um **banco dedicado
existente**. O importador cria a tabela, mas não cria o banco ou o usuário.

Ou, com Docker instalado, suba o PostgreSQL local:

```powershell
docker compose up -d postgres
Copy-Item .env.example .env
```

O exemplo `.env` conecta ao servidor do Compose:

```dotenv
DATABASE_URL=postgresql+psycopg://eletrica:eletrica_local@localhost:5432/eletrica
```

Altere usuário, senha, host e porta conforme seu servidor. Caracteres
especiais nas credenciais devem ser codificados para URL. `.env` não deve
ser versionado. A senha do Compose é apenas uma configuração local;
`POSTGRES_PASSWORD` pode ser substituída no ambiente e na URL.

Depois importe e execute:

```powershell
.\.venv\Scripts\python.exe import_excel.py 23092026_1.xlsx --station principal
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000
```

Para mudar uma `DATABASE_URL` definida anteriormente no PowerShell e
passar a usar `.env`, execute `Remove-Item Env:DATABASE_URL` se ela existir.
Variáveis do processo têm prioridade sobre `.env`.

**SQLite e PostgreSQL são alternativas, não bancos sincronizados.**
Importe o XLSX em cada banco que desejar usar. O dashboard sempre consulta
o banco apontado por `DATABASE_URL` e identifica esse banco no menu lateral.

## Importador

O comando Flask e o script independente usam o mesmo importador:

```powershell
.\.venv\Scripts\python.exe -m flask --app app import-excel 23092026_1.xlsx --station principal --sheet Folha1
```

- Lê o XLSX em streaming com openpyxl; considera dimensões incorretas no XML.
- Converte `DATE` + `TIME` em timestamp e os 14 campos em números reais.
- Usa SQLAlchemy com inserção em lotes, para PostgreSQL e SQLite.
- Executa cada arquivo em uma transação: um erro de validação reverte as
  inserções daquele arquivo, preservando importações anteriores.
- A chave primária é `(station, timestamp)`. Importações repetidas ignoram
  horários existentes, **sem substituir as leituras anteriores**.
- `--station` representa a estação física; use o mesmo identificador para
  arquivos da mesma estação. Arquivos sobrepostos com valores corrigidos
  exigem uma decisão explícita de atualização; este importador não a presume.
- A primeira aba é usada por padrão; `--sheet` permite selecionar outra.
- Cabeçalhos são comparados ignorando espaços nas extremidades, caixa e
  acentuação; campos exigidos devem existir.
- Vazios numéricos viram `NULL`; texto numérico inválido interrompe a
  importação indicando a linha pelo comando Flask.

Os dois arquivos `Teste...xlsx` também presentes na pasta não são
importados automaticamente: podem se sobrepor à fonte principal.

## Tabela `sensor_readings`

| Coluna | Tipo SQLAlchemy | Observação |
| --- | --- | --- |
| station | String(120) | Parte da chave primária |
| timestamp | DateTime | Parte da chave; horário da planilha, sem fuso |
| source_file | String(255) | Arquivo de origem |
| has_quality_issue | Boolean | Pelo menos uma variável suspeita ou vazia |
| albedo, albedo_index | Float | Indicadores de reflexão |
| solar1, solar2, solar3 | Float | Canais de radiação |
| temperature, contact_temperature, dew_point | Float | Temperaturas |
| humidity, pressure, precipitation | Float | Condições atmosféricas |
| wind_direction, wind_speed, wind_gust | Float | Vento |

Há índice por timestamp para consultas temporais. A chave composta evita
duplicatas por estação. O mapeamento completo dos cabeçalhos está em
`dashboard/metrics.py` e no dicionário visível na dashboard.

## Dashboard e critérios

- Seleção de estação e período, agregação automática/minuto/15 min/hora/dia.
- Indicadores de volume, pico de radiação, temperatura, umidade e qualidade.
- Gráficos JS de radiação, temperaturas, umidade, pressão, vento e albedo.
- Tabela paginada com todos os campos originais e exportação CSV filtrada.
- Médias por intervalo calculadas no banco; API limitada a 2.000 pontos.
- Direção do vento na API usa média circular, não média aritmética.
- Filtragem atua **por variável**, não remove toda a linha por uma falha.
- Alerta conta linhas com ao menos uma marcação sobre todas as leituras
  selecionadas, independentemente de a opção de filtragem estar ligada.
- Precipitação absoluta é apresentada como faixa e média na API; nunca
  somada como chuva por minuto. Canal constante é sinalizado na interface.
- A tabela e o CSV sempre mostram valores brutos, com marcação de qualidade.
- CSV usa `;`, vírgula decimal e UTF-8 BOM, para leitura no Excel.

Regras da visão filtrada: excluir radiação negativa; excluir vento
negativo e o código suspeito `3276,7`; direção entre 0–360; umidade 0–100;
pressão positiva; precipitação não negativa. Albedo exige Solar1 ≥ 20
e valor entre 0–1; índice exige Solar1 ≥ 20 e valor entre 0–100.
Temperatura não recebe limites físicos presumidos. Não há conversão de
unidades nem correção automática dos dados brutos. As unidades com `*`
são hipóteses, porque não foram documentadas na planilha.

## API

| GET | Resultado |
| --- | --- |
| `/api/metadata` | Estações, período total, campos e regras |
| `/api/summary` | Volume, alertas, média/extremos/contagem por variável |
| `/api/series` | Médias temporais por intervalo |
| `/api/readings` | Leituras brutas paginadas |
| `/api/export.csv` | Exportação bruta do período/estação |

Parâmetros: `station`, `start`, `end` (ISO local), `clean=1` ou `0`.
Data final sem horário inclui o dia inteiro. Data com horário inclui o
minuto informado. `/series` aceita `interval=auto|minute|15min|hour|day`
e `max_points=50..2000`. `/readings` aceita `page` e `page_size=1..200`.
Intervalos que excedem o limite são rejeitados com erro explicativo.

```text
/api/series?station=principal&start=2026-09-01&end=2026-09-23&interval=hour&clean=1
```

## Execução contínua

Para servir localmente com Waitress:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5000 app:app
```

A aplicação está configurada para uso local e não inclui autenticação.
Para publicação, adicione autenticação e HTTPS no serviço de hospedagem.
Não é necessário expor a aplicação para acessar a dashboard local.

Os gráficos usam Chart.js local. As fontes visuais são opcionais do Google
Fonts; sem internet, a interface utiliza as fontes do sistema.
Nenhum teste automatizado/TDD foi criado, conforme solicitação.

Referências: [Flask](https://flask.palletsprojects.com/en/stable/patterns/appfactories/),
[SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html),
[SQLAlchemy SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html),
[Chart.js](https://www.chartjs.org/docs/latest/getting-started/integration.html).
