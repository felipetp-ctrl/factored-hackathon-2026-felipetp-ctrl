"""Customer-facing messages in Spanish and Portuguese.

Deterministic templates filled only with verified data from the flow result. The LLM never writes
these messages, so the system cannot claim an action that did not happen."""

from __future__ import annotations

from decimal import Decimal

from dispute_ops.domain import DisputeCase, ReasonCode, Transaction
from dispute_ops.flow import FlowResult

Lang = str  # "es" | "pt"

REASON_LABEL = {
    "es": {
        ReasonCode.FRAUD_CNP: "cargo no reconocido",
        ReasonCode.FRAUD_CP: "cargo no reconocido (tarjeta extraviada o robada)",
        ReasonCode.DUPLICATE: "cobro duplicado",
        ReasonCode.INCORRECT_AMOUNT: "monto incorrecto",
        ReasonCode.NOT_RECEIVED: "producto o servicio no recibido",
        ReasonCode.CANCELLED_RECURRING: "suscripción cancelada que siguió cobrando",
    },
    "pt": {
        ReasonCode.FRAUD_CNP: "compra não reconhecida",
        ReasonCode.FRAUD_CP: "compra não reconhecida (cartão perdido ou roubado)",
        ReasonCode.DUPLICATE: "cobrança duplicada",
        ReasonCode.INCORRECT_AMOUNT: "valor incorreto",
        ReasonCode.NOT_RECEIVED: "produto ou serviço não recebido",
        ReasonCode.CANCELLED_RECURRING: "assinatura cancelada que continuou cobrando",
    },
}

QUESTIONS = {
    "es": {
        "transaction": "¿Qué compra desea disputar? Indíqueme el comercio, el monto o la fecha aproximada.",
        "reason_code": (
            "¿Qué pasó con este cargo? Por ejemplo: no lo reconoce, se cobró dos veces, el monto es "
            "incorrecto, no recibió el producto o canceló una suscripción."
        ),
        "card_in_possession": "¿Tiene la tarjeta con usted en este momento?",
        "recognizes_merchant": "¿Reconoce al comercio de esta compra?",
        "duplicate_transaction_id": "¿Cuál es el otro cargo idéntico?",
        "expected_amount": "¿Cuál era el monto correcto?",
        "expected_delivery_date": "¿En qué fecha debía recibir el producto o servicio?",
        "contacted_merchant": "¿Ya se comunicó con el comercio?",
        "cancellation_date": "¿En qué fecha canceló la suscripción?",
    },
    "pt": {
        "transaction": "Qual compra você quer contestar? Me diga a loja, o valor ou a data aproximada.",
        "reason_code": (
            "O que aconteceu com essa cobrança? Por exemplo: você não reconhece, foi cobrado duas vezes, "
            "o valor está errado, não recebeu o produto ou cancelou uma assinatura."
        ),
        "card_in_possession": "O cartão está com você neste momento?",
        "recognizes_merchant": "Você reconhece a loja dessa compra?",
        "duplicate_transaction_id": "Qual é a outra cobrança idêntica?",
        "expected_amount": "Qual era o valor correto?",
        "expected_delivery_date": "Em que data você deveria ter recebido o produto ou serviço?",
        "contacted_merchant": "Você já entrou em contato com a loja?",
        "cancellation_date": "Em que data você cancelou a assinatura?",
    },
}

T = {
    "es": {
        "greeting": "¡Hola! Soy el asistente de disputas de LATAM Bank. ¿Qué cargo de su tarjeta desea disputar?",
        "candidates": "Encontré estas compras:",
        "candidates_closest": "No encontré una compra exactamente así; estas son las más parecidas:",
        "candidates_recent": "No encontré una compra con esos datos. Estas son sus compras más recientes:",
        "candidate_one": "Encontré esta compra:",
        "pick": "¿Cuál de ellas es?",
        "pick_one": "¿Es esta? (sí/no)",
        "candidates_duplicate": "Estos son sus otros cargos en este comercio:",
        "pick_duplicate": "¿Cuál es el cargo repetido? Si ninguno lo es, cuénteme qué pasó.",
        "no_duplicate": "Sin otro cargo igual en este comercio, no es un cobro duplicado.",
        "ambiguous_no": "¿Su «no» es para la disputa o solo para el bloqueo de la tarjeta? Puede abrir la disputa sin bloquearla.",
        "invalid_expected_amount": "El monto correcto debe ser menor que el cobrado ({amount} {currency}).",
        "R-NOT-DUE": "Todavía está dentro del plazo de entrega (hasta el {expected_delivery_date}). Si no llega para esa fecha, puede abrir la disputa.",
        "R-CANCEL-AFTER": "Este cargo es del {transaction_date}, anterior a la cancelación del {cancellation_date}, así que no se puede disputar como suscripción cancelada.",
        "confirm": "Resumen: abriré una disputa por {reason} de la compra de {amount} {currency} en {merchant} del {date}. ¿Confirma? (sí/no)",
        "offer_block": "Por seguridad, también recomiendo bloquear la tarjeta usada en esta compra para evitar nuevos cargos. ¿Desea bloquearla?",
        "done": "Listo. Su disputa quedó registrada con el número de caso {case_id}.",
        "blocked": "La tarjeta fue bloqueada.",
        "not_blocked": "La tarjeta sigue activa.",
        "R-WINDOW": "No es posible disputar esta compra: tiene {age_days} días y el plazo para este tipo de disputa es de {window_days} días.",
        "R-TXN-STATUS": "No es posible disputar esta transacción porque su estado es «{transaction_status}».",
        "R-DUP-OPEN": "Ya existe una disputa abierta para esta compra (caso {open_dispute_case_id}).",
        "handoff": "Voy a transferir su caso a un especialista (referencia {case_ref}). Recibirá el resumen y los datos verificados, no necesita repetir la información.",
        "reauth": "Su sesión expiró o no es válida. Por favor, inicie sesión nuevamente para continuar.",
        "cancelled": "Entendido, no abrí ninguna disputa. ¿Puedo ayudarle con otro cargo?",
        "out_of_scope": "Por este canal solo puedo ayudar con disputas de cargos en su tarjeta. Para otras consultas use la app o hable con un asesor. ¿Desea disputar algún cargo?",
        "retry": "Tuve un problema técnico para entender su mensaje. ¿Podría repetirlo?",
        "proactive": "Detectamos una compra de {amount} {currency} en {merchant} el {date}. ¿Fue usted? (sí/no)",
        "recognized": "Gracias por confirmar. No haremos ningún cambio.",
        "goodbye": "Entendido, no hay nada que disputar. Si más adelante ve un cargo que no reconoce, estoy aquí. ¡Que tenga un buen día!",
        "goodbye_redirect": "Para esas consultas, use la app de LATAM Bank o hable con un asesor. Si más adelante necesita disputar un cargo, estoy aquí. ¡Que tenga un buen día!",
        "purchase_intro": "Sobre su compra de {amount} {currency} en {merchant} del {date}:",
        "ended": "Esta conversación terminó. Si necesita disputar otro cargo, inicie una nueva conversación.",
    },
    "pt": {
        "greeting": "Olá! Sou o assistente de contestações do LATAM Bank. Qual cobrança do seu cartão você quer contestar?",
        "candidates": "Encontrei estas compras:",
        "candidates_closest": "Não encontrei uma compra exatamente assim; estas são as mais parecidas:",
        "candidates_recent": "Não encontrei uma compra com esses dados. Estas são as suas compras mais recentes:",
        "candidate_one": "Encontrei esta compra:",
        "pick": "Qual delas é?",
        "pick_one": "É esta? (sim/não)",
        "candidates_duplicate": "Estas são as suas outras compras nessa loja:",
        "pick_duplicate": "Qual delas é a cobrança repetida? Se nenhuma for, me conte o que aconteceu.",
        "no_duplicate": "Sem outra cobrança igual nessa loja, não é uma cobrança duplicada.",
        "ambiguous_no": "Seu “não” é para a contestação ou só para o bloqueio do cartão? Dá para abrir a contestação sem bloquear.",
        "invalid_expected_amount": "O valor correto precisa ser menor que o cobrado ({amount} {currency}).",
        "R-NOT-DUE": "A entrega ainda está no prazo (até {expected_delivery_date}). Se não chegar até lá, você pode abrir a contestação.",
        "R-CANCEL-AFTER": "Esta cobrança é de {transaction_date}, antes do cancelamento em {cancellation_date}, então não pode ser contestada como assinatura cancelada.",
        "confirm": "Resumo: vou abrir uma contestação por {reason} da compra de {amount} {currency} em {merchant} do dia {date}. Confirma? (sim/não)",
        "offer_block": "Por segurança, também recomendo bloquear o cartão usado nesta compra para evitar novas cobranças. Quer bloqueá-lo?",
        "done": "Pronto. Sua contestação foi registrada com o protocolo {case_id}.",
        "blocked": "O cartão foi bloqueado.",
        "not_blocked": "O cartão continua ativo.",
        "R-WINDOW": "Não é possível contestar esta compra: ela tem {age_days} dias e o prazo para este tipo de contestação é de {window_days} dias.",
        "R-TXN-STATUS": "Não é possível contestar esta transação porque o status dela é «{transaction_status}».",
        "R-DUP-OPEN": "Já existe uma contestação aberta para esta compra (protocolo {open_dispute_case_id}).",
        "handoff": "Vou transferir seu caso para um especialista (referência {case_ref}). Ele recebe o resumo e os dados verificados, você não precisa repetir as informações.",
        "reauth": "Sua sessão expirou ou não é válida. Por favor, faça login novamente para continuar.",
        "cancelled": "Entendido, não abri nenhuma contestação. Posso ajudar com outra cobrança?",
        "out_of_scope": "Por aqui eu só consigo ajudar com contestação de cobranças no cartão. Para outros assuntos use o app ou fale com um atendente. Quer contestar alguma cobrança?",
        "retry": "Tive um problema técnico para entender sua mensagem. Pode repetir?",
        "proactive": "Identificamos uma compra de {amount} {currency} em {merchant} no dia {date}. Foi você? (sim/não)",
        "recognized": "Obrigado por confirmar. Não faremos nenhuma alteração.",
        "goodbye": "Entendido, não há nada para contestar. Se depois você vir uma cobrança que não reconhece, é só me chamar. Tenha um bom dia!",
        "goodbye_redirect": "Para esses assuntos, use o app do LATAM Bank ou fale com um atendente. Se depois precisar contestar uma cobrança, é só me chamar. Tenha um bom dia!",
        "purchase_intro": "Sobre a sua compra de {amount} {currency} em {merchant} do dia {date}:",
        "ended": "Esta conversa terminou. Se precisar contestar outra cobrança, comece uma nova conversa.",
    },
}


def _lang(lang: str | None) -> str:
    return lang if lang in T else "es"


def message(key: str, lang: str | None, **kw: object) -> str:
    return T[_lang(lang)][key].format(**kw)


# Currencies whose countries write 1.234,56 (Argentina, Colombia; Brazil for Portuguese readers).
# Mexico and USD amounts keep 1,234.56 for Spanish readers, as Mexican customers write them.
_COMMA_DECIMAL = {"ARS", "COP", "BRL"}


def fmt_amount(amount: Decimal, currency: str, lang: str | None) -> str:
    """Format an amount the way the customer reads it, so it matches what they typed."""
    text = f"{amount:,.2f}"
    if lang == "pt" or currency in _COMMA_DECIMAL:
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return text


def _txn_fields(t: Transaction, lang: str | None = None) -> dict[str, object]:
    return {
        "amount": fmt_amount(t.amount, t.currency, _lang(lang)), "currency": t.currency,
        "merchant": t.merchant_name or "—", "date": t.transaction_date.strftime("%d/%m/%Y"),
    }


def purchase_intro(t: Transaction, lang: str | None) -> str:
    return message("purchase_intro", lang, **_txn_fields(t, lang))


def proactive_prompt(t: Transaction, lang: str | None) -> str:
    return message("proactive", lang, **_txn_fields(t, lang))


def render(result: FlowResult, lang: str | None, *, transaction: Transaction | None, reason: ReasonCode | None) -> str:
    lang = _lang(lang)
    if result.action == "ask":
        lines: list[str] = []
        if result.candidates:
            one = len(result.candidates) == 1
            duplicate = result.candidates_note == "duplicate"
            header = {"closest": "candidates_closest", "recent": "candidates_recent",
                      "duplicate": "candidates_duplicate"}.get(result.candidates_note or "", "candidate_one" if one else "candidates")
            lines.append(T[lang][header])
            for i, c in enumerate(result.candidates, 1):
                f = _txn_fields(c, lang)
                when = c.transaction_date.strftime("%H:%M")
                lines.append(f"{i}) {f['merchant']} · {f['amount']} {f['currency']} · {f['date']} {when} ({c.transaction_id})")
            lines.append(T[lang]["pick_duplicate" if duplicate else "pick_one" if one else "pick"])
        else:
            if result.candidates_note == "no_duplicate":
                lines.append(T[lang]["no_duplicate"])
            elif result.candidates_note == "invalid_expected_amount" and transaction is not None:
                lines.append(message("invalid_expected_amount", lang, **_txn_fields(transaction, lang)))
            lines.extend(QUESTIONS[lang].get(field, field) for field in result.ask_for)
        return "\n".join(lines)
    if result.action == "confirm":
        assert transaction is not None and reason is not None
        text = message("confirm", lang, reason=REASON_LABEL[lang][reason], **_txn_fields(transaction, lang))
        return f"{text}\n{T[lang]['offer_block']}" if result.offer_block_card else text
    if result.action == "done":
        case: DisputeCase = result.case  # type: ignore[assignment]
        text = message("done", lang, case_id=case.case_id)
        if result.card is not None:
            text += " " + T[lang]["blocked" if result.card.product_status == "Blocked" else "not_blocked"]
        return text
    if result.action == "ineligible":
        rule = result.policy.rule_ids[0]  # type: ignore[union-attr]
        inputs = {k: (f"{v[8:10]}/{v[5:7]}/{v[:4]}" if k.endswith("_date") and isinstance(v, str) else v)
                  for k, v in result.policy.inputs.items()}  # type: ignore[union-attr]
        return message(rule, lang, **inputs)
    if result.action == "handoff":
        return message("handoff", lang, case_ref=result.handoff.case_ref)  # type: ignore[union-attr]
    if result.action == "reauth":
        return T[lang]["reauth"]
    return T[lang]["cancelled"]
