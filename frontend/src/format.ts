export const CURRENCY = "Br";

const formatterCache = new Map<number, Intl.NumberFormat>();

export function money(
  value: number | string | null | undefined,
  decimals = 0,
): string {
  const amount = Number(value ?? 0);
  let formatter = formatterCache.get(decimals);
  if (!formatter) {
    formatter = new Intl.NumberFormat("ru-RU", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    formatterCache.set(decimals, formatter);
  }
  return `${formatter.format(amount)} ${CURRENCY}`;
}
