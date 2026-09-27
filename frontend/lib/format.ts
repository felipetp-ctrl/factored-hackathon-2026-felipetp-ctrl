import type { Lang } from "./api";

// Same convention as the bank's replies (backend responses.fmt_amount): Argentina and Colombia write 1.234,56,
// Mexico and USD amounts keep 1,234.56 for Spanish readers, Portuguese readers get 1.234,56.
const LOCALE_BY_CURRENCY: Record<string, string> = { ARS: "es-AR", COP: "es-CO", MXN: "es-MX", USD: "es-MX" };

export function money(amount: string | number, currency: string, lang: Lang): string {
  const locale = lang === "pt" ? "pt-BR" : LOCALE_BY_CURRENCY[currency] ?? "es-MX";
  return new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(amount));
}

export function day(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function dayTime(iso: string): string {
  return `${day(iso)} ${iso.slice(11, 16)}`;
}

export const FLAG: Record<string, string> = { Argentina: "AR", Colombia: "CO", Mexico: "MX" };
