export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(value) + " ₽";
}

export function moneyCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 1_000_000) {
    return (value / 1_000_000).toFixed(2).replace(".", ",") + " млн ₽";
  }
  if (Math.abs(value) >= 1_000) {
    return Math.round(value / 1_000) + " тыс ₽";
  }
  return money(value);
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits).replace(".", ",")}%`;
}

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits).replace(".", ",");
}

export function dateRu(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function dateShort(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
  }).format(date);
}

export function relativeDays(days: number): string {
  if (days === 0) return "сегодня";
  if (days === 1) return "завтра";
  if (days < 0) return `${Math.abs(days)} дн. назад`;
  return `через ${days} дн.`;
}

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}
