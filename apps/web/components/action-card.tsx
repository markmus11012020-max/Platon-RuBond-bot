"use client";

import { Check, ShieldAlert, Sparkles } from "lucide-react";

import { money, pct } from "@/lib/format";
import type { ActionCard } from "@/lib/types";

const EFFECT_LABELS: Record<string, string> = {
  yield_delta_pct: "Доходность",
  duration_delta_years: "Дюрация",
  free_cash_rub: "Свободно",
  rating_change: "Рейтинг",
  concentration_pct: "Концентрация",
  limit_pct: "Лимит",
};

function effectValue(key: string, value: string | number): string {
  if (key === "yield_delta_pct" && typeof value === "number") {
    return `${value > 0 ? "+" : ""}${pct(value, 2)}`;
  }
  if (key === "duration_delta_years" && typeof value === "number") {
    return `${value > 0 ? "+" : ""}${value.toFixed(2).replace(".", ",")} г.`;
  }
  if (key === "free_cash_rub" && typeof value === "number") {
    return money(value);
  }
  if (
    (key === "concentration_pct" || key === "limit_pct") &&
    typeof value === "number"
  ) {
    return pct(value, 1);
  }
  return String(value);
}

export function ActionCardView({
  action,
  onConfirm,
  confirming,
}: {
  action: ActionCard;
  onConfirm?: () => void;
  confirming?: boolean;
}) {
  const confirmed = action.status === "confirmed";
  const review = action.kind === "review";
  return (
    <div className="action-card">
      <div className="action-head">
        <div>
          <div className={`chip ${review ? "rose" : "gold"}`}>
            {review ? <ShieldAlert size={11} /> : <Sparkles size={11} />}
            {review ? "Риск-проверка" : "План агента"}
          </div>
          <div className="action-title" style={{ marginTop: 9 }}>
            {action.title}
          </div>
        </div>
        {confirmed ? (
          <div className="chip mint">
            <Check size={12} />
            Зафиксировано
          </div>
        ) : (
          <div className="chip">{review ? "Без сделки" : "Sandbox"}</div>
        )}
      </div>

      <div className="action-desc">{action.description}</div>

      <div className="action-legs">
        {action.legs.map((leg) => (
          <div className="action-leg" key={`${leg.side}-${leg.isin}`}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className={`leg-side ${leg.side}`}>
                {leg.side === "sell" ? "Продать" : "Купить"}
              </span>
              <div>
                <div style={{ fontWeight: 700 }}>{leg.name}</div>
                <div className="tiny muted">
                  {leg.quantity} шт. · {pct(leg.price_pct, 1)}
                </div>
              </div>
            </div>
            <div style={{ fontWeight: 760, fontVariantNumeric: "tabular-nums" }}>
              {money(leg.amount_rub)}
            </div>
          </div>
        ))}
      </div>

      {Object.keys(action.expected_effect).length ? (
        <div className="action-effect">
          {Object.entries(action.expected_effect)
            .slice(0, 3)
            .map(([key, value]) => (
              <div className="effect" key={key}>
                <div className="effect-label">
                  {EFFECT_LABELS[key] || key}
                </div>
                <div className="effect-value">{effectValue(key, value)}</div>
              </div>
            ))}
        </div>
      ) : null}

      {action.risk_notes.length ? (
        <ul className="risk-notes">
          {action.risk_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}

      {!confirmed && onConfirm ? (
        <button
          type="button"
          className="primary-button"
          onClick={onConfirm}
          disabled={confirming}
        >
          {confirming
            ? "Фиксирую..."
            : review
              ? "Зафиксировать проверку"
              : "Подтвердить в sandbox"}
        </button>
      ) : null}

      {confirmed ? (
        <div
          className="tiny muted"
          style={{ marginTop: 10, display: "flex", gap: 6, alignItems: "center" }}
        >
          <ShieldAlert size={13} />
          {review
            ? "Проверка записана в аудит. Сделка не выставлялась."
            : "Операция записана в аудит. В production здесь будет MCP order-tool."}
        </div>
      ) : null}
    </div>
  );
}
