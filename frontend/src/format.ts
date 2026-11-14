export const CURRENCY = "Br";

export function money(
  value: number | string | null | undefined,
  decimals = 0,
): string {
  const amount = Number(value ?? 0);
  return `${amount.toFixed(decimals)} ${CURRENCY}`;
}
