import dayjs, { Dayjs } from "dayjs";
import type { BillingUnit, Equipment } from "./api/types";

const WEEKDAY_KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"] as const;

function toMinutes(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + (minutes || 0);
}

function formatSlot(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(
    minutes % 60,
  ).padStart(2, "0")}`;
}

export function slotsForDate(item: Equipment | undefined, date: Dayjs | null): string[] {
  if (!item) return [];
  if (!item.working_hours) {
    const all: string[] = [];
    for (let minutes = 0; minutes < 24 * 60; minutes += 30) all.push(formatSlot(minutes));
    return all;
  }
  if (!date) return [];
  const key = WEEKDAY_KEYS[date.day()];
  const intervals = item.working_hours[key] ?? [];
  const slots: string[] = [];
  for (const [open, close] of intervals) {
    const from = toMinutes(open);
    const to = toMinutes(close);
    for (let minutes = from; minutes < to; minutes += 30) slots.push(formatSlot(minutes));
  }
  return slots;
}

export function pickBillingUnit(
  item: Equipment,
  amount: number,
  unit: "hour" | "day",
): BillingUnit {
  const hasHour = item.price_per_hour !== null;
  const hasDay = item.price_per_day !== null;
  if (!hasDay) return "hour";
  if (!hasHour) return "day";
  const hours = unit === "day" ? amount * 24 : amount;
  return hours >= 24 ? "day" : "hour";
}

export function durationLimits(item: Equipment, unit: "hour" | "day") {
  return unit === "day"
    ? { min: item.min_days, max: item.max_days }
    : { min: item.min_hours, max: item.max_hours };
}

export function combineDateTime(date: Dayjs | null, time: string | null): Dayjs | null {
  if (!date || !time) return null;
  const [hours, minutes] = time.split(":").map(Number);
  return dayjs(date).hour(hours).minute(minutes).second(0).millisecond(0);
}
