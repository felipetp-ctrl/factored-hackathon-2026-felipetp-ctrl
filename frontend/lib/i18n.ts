import type { Lang, Reply } from "./api";

export const T = {
  es: {
    hello: (name: string) => `Hola, ${name}`,
    tabs: { home: "Inicio", chat: "Disputar", cases: "Mis disputas" },
    form: {
      title: "Disputa de un cargo", yourCase: "Su caso", charge: "Compra", reason: "Qué pasó", details: "Detalles", result: "Resultado",
      fromBank: "registro del banco", fromText: "leído de lo que escribió", missing: "falta", notYet: "—",
      now: "Ahora", write: "Escriba con sus palabras…", history: "Ver lo escrito", start: "Toque “No reconozco” en una compra en Inicio, o describa el problema:",
      yes: "sí", no: "no", done: "Disputa abierta y confirmada", person: "Con un especialista", closed: "Sin disputa",
      evidence: { card_in_possession: "Tarjeta con usted", recognizes_merchant: "Reconoce el comercio", duplicate_transaction_id: "El otro cargo",
        expected_amount: "Monto correcto", expected_delivery_date: "Fecha de entrega", contacted_merchant: "Habló con el comercio", cancellation_date: "Fecha de cancelación" } as Record<string, string>,
    },
    card: "Tarjeta", active: "Activa", blocked: "Bloqueada",
    recent: "Compras recientes", noMerchant: "Comercio sin nombre", dispute: "No reconozco",
    inDispute: "En disputa", reversed: "Revertida", pending: "Pendiente",
    alertTitle: "¿Reconoce esta compra?", alertBody: "Nuestro sistema de fraude la marcó como sospechosa.",
    alertYes: "Sí, fui yo", alertNo: "No fui yo",
    askAssistant: "Hablar con el asistente", startHint: "Toque “No reconozco” en una compra, o escriba aquí.",
    placeholder: "Escriba su mensaje", send: "Enviar", why: "¿Por qué?",
    confirm: ["Sí, confirmo", "No, cancelar"],
    confirmBlock: ["Sí, y bloqueen la tarjeta", "Sí, sin bloquear la tarjeta", "No, cancelar"],
    yesNo: ["Sí", "No"],
    reauth: "Su sesión expiró", reauthBtn: "Entrar de nuevo y reenviar", reauthDone: "Entró de nuevo. Mensaje reenviado.",
    noCases: "No tiene disputas abiertas. Si ve un cargo que no reconoce, tóquelo en Inicio.",
    openedBy: { assistant: "Abierta por el asistente", agent: "Abierta por un especialista" },
    caseStatus: { Open: "En revisión" } as Record<string, string>,
    reason: {
      FRAUD_CNP: "Cargo no reconocido", FRAUD_CP: "Tarjeta perdida o robada", DUPLICATE: "Cobro duplicado",
      INCORRECT_AMOUNT: "Monto incorrecto", NOT_RECEIVED: "Producto no recibido", CANCELLED_RECURRING: "Suscripción cancelada",
    } as Record<string, string>,
    interpretedBy: { claude: "Entendido por IA", rules: "Entendido por reglas (modo de reserva)", none: "" },
    ended: "Conversación terminada", newChat: "Nueva conversación",
  },
  pt: {
    hello: (name: string) => `Olá, ${name}`,
    tabs: { home: "Início", chat: "Contestar", cases: "Minhas contestações" },
    form: {
      title: "Contestação de uma cobrança", yourCase: "Seu caso", charge: "Compra", reason: "O que aconteceu", details: "Detalhes", result: "Resultado",
      fromBank: "registro do banco", fromText: "lido do que você escreveu", missing: "falta", notYet: "—",
      now: "Agora", write: "Escreva com suas palavras…", history: "Ver o que foi escrito", start: "Toque em “Não reconheço” numa compra no Início, ou descreva o problema:",
      yes: "sim", no: "não", done: "Contestação aberta e confirmada", person: "Com um especialista", closed: "Sem contestação",
      evidence: { card_in_possession: "Cartão com você", recognizes_merchant: "Reconhece a loja", duplicate_transaction_id: "A outra cobrança",
        expected_amount: "Valor correto", expected_delivery_date: "Data de entrega", contacted_merchant: "Falou com a loja", cancellation_date: "Data do cancelamento" } as Record<string, string>,
    },
    card: "Cartão", active: "Ativo", blocked: "Bloqueado",
    recent: "Compras recentes", noMerchant: "Loja sem nome", dispute: "Não reconheço",
    inDispute: "Em contestação", reversed: "Estornada", pending: "Pendente",
    alertTitle: "Você reconhece esta compra?", alertBody: "Nosso sistema antifraude marcou esta compra como suspeita.",
    alertYes: "Sim, fui eu", alertNo: "Não fui eu",
    askAssistant: "Falar com o assistente", startHint: "Toque em “Não reconheço” numa compra, ou escreva aqui.",
    placeholder: "Escreva sua mensagem", send: "Enviar", why: "Por quê?",
    confirm: ["Sim, confirmo", "Não, cancelar"],
    confirmBlock: ["Sim, e bloqueiem o cartão", "Sim, sem bloquear o cartão", "Não, cancelar"],
    yesNo: ["Sim", "Não"],
    reauth: "Sua sessão expirou", reauthBtn: "Entrar de novo e reenviar", reauthDone: "Você entrou de novo. Mensagem reenviada.",
    noCases: "Você não tem contestações abertas. Se vir uma cobrança que não reconhece, toque nela em Início.",
    openedBy: { assistant: "Aberta pelo assistente", agent: "Aberta por um especialista" },
    caseStatus: { Open: "Em análise" } as Record<string, string>,
    reason: {
      FRAUD_CNP: "Compra não reconhecida", FRAUD_CP: "Cartão perdido ou roubado", DUPLICATE: "Cobrança duplicada",
      INCORRECT_AMOUNT: "Valor incorreto", NOT_RECEIVED: "Produto não recebido", CANCELLED_RECURRING: "Assinatura cancelada",
    } as Record<string, string>,
    interpretedBy: { claude: "Entendido por IA", rules: "Entendido por regras (modo de reserva)", none: "" },
    ended: "Conversa encerrada", newChat: "Nova conversa",
  },
};

const FIELD = {
  es: {
    transaction: "cuál es la compra", reason_code: "qué pasó con el cargo", card_in_possession: "si tiene la tarjeta",
    recognizes_merchant: "si reconoce el comercio", duplicate_transaction_id: "cuál es el otro cargo",
    expected_amount: "el monto correcto", expected_delivery_date: "la fecha de entrega",
    contacted_merchant: "si habló con el comercio", cancellation_date: "la fecha de cancelación",
  },
  pt: {
    transaction: "qual é a compra", reason_code: "o que aconteceu com a cobrança", card_in_possession: "se o cartão está com você",
    recognizes_merchant: "se você reconhece a loja", duplicate_transaction_id: "qual é a outra cobrança",
    expected_amount: "o valor correto", expected_delivery_date: "a data de entrega",
    contacted_merchant: "se você falou com a loja", cancellation_date: "a data do cancelamento",
  },
} as Record<Lang, Record<string, string>>;

const HANDOFF = {
  es: {
    amount_above_threshold: "El monto supera US$ 450 (regla R-HO-AMOUNT). Casos de ese valor los revisa una persona.",
    repeat_complainer: "Hay reclamos anteriores en la cuenta (R-HO-REPEAT); una persona revisa el historial.",
    dispute_velocity: "Hubo varias disputas en 30 días (R-HO-VELOCITY).",
    very_negative_sentiment: "Notamos mucha molestia; una persona atiende mejor este caso (R-HO-SENTIMENT).",
    regulatory_or_legal_threat: "Mencionó un regulador o una acción legal (R-HO-REGULATOR).",
    implausible_amount_claim: "El monto correcto indicado es menos de la mitad del cargo; una persona lo revisa (R-HO-AMOUNT-GAP).",
    low_classifier_confidence: "No quedó claro el motivo del reclamo; mejor que lo vea una persona (R-HO-LOWCONF).",
    customer_requested_human: "Usted pidió hablar con una persona.",
    suspicious_access: "Se pidió una compra que no está disponible para esta sesión. Por seguridad pasa a una persona.",
    invalid_transaction_references: "Las referencias indicadas no corresponden a sus compras.",
    clarification_exhausted: "Después de dos intentos no logramos identificar el dato; una persona sigue desde aquí.",
    tool_failure: "Un sistema del banco no respondió. No informamos nada como hecho sin confirmarlo.",
    verification_failed: "No pudimos confirmar la acción leyéndola de vuelta, así que no la damos por hecha.",
    nlu_unavailable: "El servicio de interpretación no estaba disponible.",
  },
  pt: {
    amount_above_threshold: "O valor passa de US$ 450 (regra R-HO-AMOUNT). Casos desse valor são revisados por uma pessoa.",
    repeat_complainer: "Há reclamações anteriores na conta (R-HO-REPEAT); uma pessoa revisa o histórico.",
    dispute_velocity: "Houve várias contestações em 30 dias (R-HO-VELOCITY).",
    very_negative_sentiment: "Percebemos muita insatisfação; uma pessoa atende melhor este caso (R-HO-SENTIMENT).",
    regulatory_or_legal_threat: "Você mencionou um órgão regulador ou ação judicial (R-HO-REGULATOR).",
    implausible_amount_claim: "O valor correto informado é menos da metade da cobrança; uma pessoa revisa (R-HO-AMOUNT-GAP).",
    low_classifier_confidence: "O motivo não ficou claro; é melhor uma pessoa ver (R-HO-LOWCONF).",
    customer_requested_human: "Você pediu para falar com uma pessoa.",
    suspicious_access: "Foi pedida uma compra que não está disponível para esta sessão. Por segurança, passa para uma pessoa.",
    invalid_transaction_references: "As referências informadas não correspondem às suas compras.",
    clarification_exhausted: "Depois de duas tentativas não conseguimos identificar o dado; uma pessoa continua daqui.",
    tool_failure: "Um sistema do banco não respondeu. Nada é informado como feito sem confirmação.",
    verification_failed: "Não conseguimos confirmar a ação lendo de volta, então não a damos como feita.",
    nlu_unavailable: "O serviço de interpretação não estava disponível.",
  },
} as Record<Lang, Record<string, string>>;

/** Plain-language reason for a bank reply, built only from the policy decision and the flow outcome. */
export function why(r: Reply, lang: Lang): string {
  const es = lang === "es";
  const p = r.policy;
  switch (r.action) {
    case "ask":
      if (r.candidates.length) return es
        ? "Hay varias compras parecidas y no elijo por usted. Solo busco entre sus propias compras."
        : "Há várias compras parecidas e eu não escolho por você. Só procuro entre as suas próprias compras.";
      if (p?.missing_evidence?.length) return es
        ? `La política ${p.policy_version} pide ${p.missing_evidence.map((f) => FIELD.es[f] ?? f).join(" y ")} para este tipo de disputa. Nada se decide con suposiciones.`
        : `A política ${p.policy_version} pede ${p.missing_evidence.map((f) => FIELD.pt[f] ?? f).join(" e ")} para este tipo de contestação. Nada é decidido com suposições.`;
      return es
        ? `Falta saber ${r.ask_for.map((f) => FIELD.es[f] ?? f).join(" y ")}: el tipo de problema define el plazo y la evidencia que pide la política.`
        : `Falta saber ${r.ask_for.map((f) => FIELD.pt[f] ?? f).join(" e ")}: o tipo de problema define o prazo e a evidência que a política pede.`;
    case "confirm":
      return es
        ? `Cumple la política (${p?.rule_ids.join(", ") ?? "R-ELIGIBLE"}): está dentro del plazo y el monto permite resolverlo sin una persona. Aun así, nada se ejecuta sin su confirmación.`
        : `Cumpre a política (${p?.rule_ids.join(", ") ?? "R-ELIGIBLE"}): está dentro do prazo e o valor permite resolver sem uma pessoa. Mesmo assim, nada é feito sem a sua confirmação.`;
    case "done":
      return es
        ? "La disputa se registró y se confirmó leyéndola de vuelta del sistema antes de avisarle. Aparece en Mis disputas."
        : "A contestação foi registrada e confirmada lendo de volta no sistema antes de avisar você. Ela aparece em Minhas contestações.";
    case "ineligible": {
      const rule = p?.rule_ids[0];
      if (rule === "R-WINDOW") return es
        ? `Regla R-WINDOW: la compra tiene ${p?.inputs.age_days} días y el plazo es ${p?.inputs.window_days}.`
        : `Regra R-WINDOW: a compra tem ${p?.inputs.age_days} dias e o prazo é ${p?.inputs.window_days}.`;
      if (rule === "R-TXN-STATUS") return es
        ? `Regla R-TXN-STATUS: solo se disputan compras aprobadas o pendientes (esta está «${p?.inputs.transaction_status}»).`
        : `Regra R-TXN-STATUS: só se contestam compras aprovadas ou pendentes (esta está «${p?.inputs.transaction_status}»).`;
      return es ? "Regla R-DUP-OPEN: ya hay una disputa abierta para esta compra." : "Regra R-DUP-OPEN: já existe uma contestação aberta para esta compra.";
    }
    case "handoff":
      return (r.handoff?.reason_for_handoff ?? []).map((x) => HANDOFF[lang][x] ?? x).join(" ")
        + (es ? " El especialista recibe los datos verificados, no la conversación entera."
              : " O especialista recebe os dados verificados, não a conversa inteira.");
    case "out_of_scope":
      return es ? "Este canal atiende solo disputas de cargos. No toca ningún caso para otras consultas."
                : "Este canal atende só contestações de cobranças. Não mexe em nenhum caso para outros assuntos.";
    case "cancelled":
      return es ? "No se abrió nada: usted no necesitaba una disputa o no confirmó." : "Nada foi aberto: você não precisava de uma contestação ou não confirmou.";
    case "reauth":
      return es ? "La sesión venció. Sin sesión válida no se consulta ni se hace nada." : "A sessão expirou. Sem sessão válida nada é consultado nem feito.";
    case "retry":
      return es ? "El servicio de interpretación falló; se pide repetir en lugar de adivinar." : "O serviço de interpretação falhou; pedimos para repetir em vez de adivinhar.";
    default:
      return "";
  }
}

export function quickReplies(r: Reply | null, lang: Lang): string[] {
  if (!r) return [];
  const t = T[lang];
  if (["done", "handoff", "ineligible", "cancelled"].includes(r.action) || r.state === "CANCELLED") return [];
  if (r.action === "confirm") return r.offer_block_card ? t.confirmBlock : t.confirm;
  const yesNo = ["card_in_possession", "recognizes_merchant", "contacted_merchant"];
  if (r.action === "ask" && !r.candidates.length && r.ask_for.length === 1 && yesNo.includes(r.ask_for[0])) return t.yesNo;
  return [];
}
