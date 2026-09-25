"""Customer-facing messages in Spanish and Portuguese.

Deterministic templates filled only with verified data from the flow result. The LLM never writes
these messages, so the system cannot claim an action that did not happen."""

from __future__ import annotations

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
        "pick": "¿Cuál de ellas es?",
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
    },
    "pt": {
        "greeting": "Olá! Sou o assistente de contestações do LATAM Bank. Qual cobrança do seu cartão você quer contestar?",
        "candidates": "Encontrei estas compras:",
        "pick": "Qual delas é?",
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
    },
}


def _lang(lang: str | None) -> str:
    return lang if lang in T else "es"


def message(key: str, lang: str | None, **kw: object) -> str:
    return T[_lang(lang)][key].format(**kw)


def _txn_fields(t: Transaction) -> dict[str, object]:
    return {
        "amount": f"{t.amount:,.2f}", "currency": t.currency,
        "merchant": t.merchant_name or "—", "date": t.transaction_date.date().isoformat(),
    }


def proactive_prompt(t: Transaction, lang: str | None) -> str:
    return message("proactive", lang, **_txn_fields(t))


def render(result: FlowResult, lang: str | None, *, transaction: Transaction | None, reason: ReasonCode | None) -> str:
    lang = _lang(lang)
    if result.action == "ask":
        lines: list[str] = []
        if result.candidates:
            lines.append(T[lang]["candidates"])
            for i, c in enumerate(result.candidates, 1):
                f = _txn_fields(c)
                lines.append(f"{i}) {f['merchant']} · {f['amount']} {f['currency']} · {f['date']} ({c.transaction_id})")
            lines.append(T[lang]["pick"])
        else:
            lines.extend(QUESTIONS[lang].get(field, field) for field in result.ask_for)
        return "\n".join(lines)
    if result.action == "confirm":
        assert transaction is not None and reason is not None
        text = message("confirm", lang, reason=REASON_LABEL[lang][reason], **_txn_fields(transaction))
        return f"{text}\n{T[lang]['offer_block']}" if result.offer_block_card else text
    if result.action == "done":
        case: DisputeCase = result.case  # type: ignore[assignment]
        text = message("done", lang, case_id=case.case_id)
        if result.card is not None:
            text += " " + T[lang]["blocked" if result.card.product_status == "Blocked" else "not_blocked"]
        return text
    if result.action == "ineligible":
        rule = result.policy.rule_ids[0]  # type: ignore[union-attr]
        return message(rule, lang, **result.policy.inputs)  # type: ignore[union-attr]
    if result.action == "handoff":
        return message("handoff", lang, case_ref=result.handoff.case_ref)  # type: ignore[union-attr]
    if result.action == "reauth":
        return T[lang]["reauth"]
    return T[lang]["cancelled"]
