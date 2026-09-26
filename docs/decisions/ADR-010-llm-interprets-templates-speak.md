# ADR-010 — O LLM interpreta; templates falam
- **Status:** aceito · **Data:** 2026-09-26

## Contexto
O desafio pede "report only actions whose outcomes the system has verified" e que a política seja aplicada fora da prosa do modelo.

## Decisão
- O Claude Haiku 4.5 transforma a mensagem, já redigida pelo gateway, num objeto estruturado validado por Pydantic (`NluResult`). Ele não chama tools de escrita e não escreve as respostas.
- As respostas ao cliente saem de templates ES/PT preenchidos só com dados verificados: protocolo lido de volta, status do cartão lido de volta, regra e números da política.
- **Isso substitui, por ora, o spec (§3), que previa o Claude como agente com tools de leitura.** A extração estruturada mostrou-se suficiente, é mais barata e é avaliável.

## Alternativas consideradas
- **LLM gera a resposta livre:** mais natural, mas pode afirmar ações inexistentes; exigiria um verificador extra.
- **Agente com tools de leitura:** mais flexível, porém com mais variância e mais custo.

## Consequências
- Nenhuma resposta pode inventar protocolo ou bloqueio; o oracle verifica isso (`fabricated_case_id`).
- As respostas são menos fluidas. A lista de candidatas precisou mostrar a hora (bug encontrado na avaliação dev).
- A mensagem do cliente vai delimitada como dado, com o HTML escapado; sinais de injection vão como contexto, sem conceder nem remover permissões.
