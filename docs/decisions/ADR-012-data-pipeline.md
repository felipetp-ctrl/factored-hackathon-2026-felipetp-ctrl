# ADR-012 — Pipeline de dados: contratos em SQL no DuckDB, ingestão incremental, silver recomputada
- **Status:** aceito · **Data:** 2026-09-26 · substitui a parte "Pandera" do ADR-006

## Contexto
São cerca de 19 milhões de linhas em CSV particionado por dia, com duplicatas, nulos, chegadas atrasadas e mudança de schema intencionais. Os valores reais divergem do dicionário (ex.: `branches.country = "México"`, `geographic_zone = "Urbana"`, `document_type = "Pasaporte"`).

## Decisão
- **Contratos declarativos** (`pipeline/contracts.py`): tipo, obrigatoriedade, domínio, faixa, PK, ordem "mais recente vence" e FKs, extraídos do dicionário v1.0.0. A checagem roda em SQL no DuckDB, não em Pandera, porque validar 5 milhões de linhas em pandas seria lento e caro em memória.
- **Bronze:** texto bruto e linhagem (`_source_file`, `_ingested_at`, `_batch_id`), um Parquet por lote. Só lê arquivos novos ou alterados (tamanho e mtime em `_state/bronze_files.json`). Linhas malformadas são contadas (rejects), não descartadas em silêncio.
- **Silver:** recomputada a partir de todo o bronze a cada execução:
  - tipos via `TRY_CAST`, com as falhas contadas;
  - dedup por PK, preferindo o `process_date`/`last_updated` mais recente e depois a ingestão mais recente. Isso resolve chegadas atrasadas e correções reentregues **por construção**;
  - FK órfã obrigatória vai para quarentena; FK órfã opcional é anulada, e ambas são contadas.
- **Gold:** `card_products`, `card_transactions`, `customer_dim` (com reincidência), `dispute_complaints`, `fraud_alert_candidates`.
- **Export:** amostra determinística de clientes para o SQLite da demo (`DEMO_DB`), usada como cópia privada pela API.
- **Linhagem e freshness:** um manifest por execução, com contagens por camada e achados de contrato. Política proposta: batch diário após o fechamento do `process_date`; atrasos são absorvidos na execução seguinte.

## Consequências
- A reexecução sem arquivos novos é idempotente (testada).
- O teste de correção de update usa uma **fixture sintética rotulada** (`tests/fixtures/raw_mini`): chegada atrasada de um dia anterior, correção reentregue e coluna nova. Também existe uma versão anterior real do dataset (`data_backup_20260831/`) para validar isso com dado do organizador.
- Recalcular a silver inteira é O(tamanho do bronze): segundos com 5M linhas no DuckDB; em escala maior seria MERGE por partição.
- Os domínios em espanhol que divergem do dicionário são reportados como violação, não "corrigidos" em silêncio. Normalizar é uma decisão de negócio pendente.
