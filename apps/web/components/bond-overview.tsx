"use client";

import {
  ArrowUpRight,
  CalendarDays,
  CircleDollarSign,
  Gauge,
  ScanSearch,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { AllocationChart, RatingBars, YieldDurationChart } from "@/components/charts";
import { dateShort, money, moneyCompact, num, pct, relativeDays } from "@/lib/format";
import type { BondOverview } from "@/lib/types";

export function BondOverviewView({
  data,
  onAsk,
  onOpenChat,
}: {
  data: BondOverview;
  onAsk: (prompt: string) => void;
  onOpenChat: () => void;
}) {
  const { summary } = data;
  const positive = summary.profit_rub >= 0;

  return (
    <>
      <section className="card hero">
        <div className="hero-top">
          <div>
            <div className="eyebrow">
              <span className="eyebrow-dot" />
              Портфель · T-Invest Sandbox
            </div>
            <div className="metric-label" style={{ marginTop: 14 }}>
              Стоимость портфеля
            </div>
            <div className="metric-value">{money(summary.total_value_rub)}</div>
            <div className={`pnl ${positive ? "" : "negative"}`}>
              {positive ? <TrendingUp size={13} /> : <ShieldAlert size={13} />}
              {positive ? "+" : ""}
              {money(summary.profit_rub)} за период
            </div>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onOpenChat}
            aria-label="Открыть агента"
            style={{ flex: "0 0 auto" }}
          >
            <Sparkles size={18} style={{ color: "var(--mint)" }} />
          </button>
        </div>

        <div className="hero-grid">
          <div className="stat">
            <div className="metric-label">YTM</div>
            <div className="stat-value">{pct(summary.weighted_ytm_pct)}</div>
          </div>
          <div className="stat">
            <div className="metric-label">Дюрация</div>
            <div className="stat-value">
              {num(summary.weighted_duration_years)} г.
            </div>
          </div>
          <div className="stat">
            <div className="metric-label">Купон / год</div>
            <div className="stat-value">{moneyCompact(summary.annual_coupon_rub)}</div>
          </div>
        </div>
      </section>

      <div className="suggestions" style={{ marginTop: 12 }}>
        {[
          "Утренний брифинг",
          "Где риск?",
          "Предложи замену",
          "Что с купонами?",
        ].map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="suggestion"
            onClick={() => onAsk(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>

      <section className="section">
        <div className="section-head">
          <div>
            <div className="eyebrow">
              <span className="eyebrow-dot" />
              Что важно
            </div>
            <h2 className="h2" style={{ marginTop: 6 }}>
              Фокус на сегодня
            </h2>
          </div>
          <button type="button" className="link-button" onClick={() => onAsk("Где риск?")}>
            Разобрать риски
          </button>
        </div>
        <div className="insight-list">
          {data.insights.map((insight, index) => (
            <div className="insight" key={insight}>
              <span className="insight-index">{String(index + 1).padStart(2, "0")}</span>
              <span>{insight}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="section two-col">
        <div className="card chart-card">
          <div className="section-head" style={{ marginBottom: 2 }}>
            <div>
              <div className="h3">Структура портфеля</div>
              <div className="tiny muted" style={{ marginTop: 4 }}>
                {summary.positions_count} выпусков · {pct(summary.weighted_ytm_pct)} YTM
              </div>
            </div>
            <CircleDollarSign size={17} style={{ color: "var(--gold)" }} />
          </div>
          <AllocationChart data={data.allocation} />
        </div>

        <div className="card chart-card">
          <div className="section-head" style={{ marginBottom: 2 }}>
            <div>
              <div className="h3">Доходность и дюрация</div>
              <div className="tiny muted" style={{ marginTop: 4 }}>
                Размер точки — доля в портфеле
              </div>
            </div>
            <Gauge size={17} style={{ color: "var(--mint)" }} />
          </div>
          <YieldDurationChart positions={data.positions} />
          <div className="chart-legend">
            <div className="legend-item">
              <span className="legend-dot" style={{ background: "#7dd3fc" }} />
              AAA / AA
            </div>
            <div className="legend-item">
              <span className="legend-dot" style={{ background: "#38d9a9" }} />
              A
            </div>
            <div className="legend-item">
              <span className="legend-dot" style={{ background: "#f6c453" }} />
              BBB и ниже
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <div className="h2">Позиции</div>
            <div className="tiny muted" style={{ marginTop: 4 }}>
              {data.positions.length} бумаг · данные на {dateShort(data.as_of)}
            </div>
          </div>
          <button type="button" className="link-button" onClick={() => onAsk("Покажи портфель")}>
            Спросить агента
          </button>
        </div>
        <div className="position-list">
          {data.positions.map((position) => (
            <div className="position" key={position.isin}>
              <div style={{ minWidth: 0 }}>
                <div className="position-name">
                  <span
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {position.name}
                  </span>
                  <span
                    className={`rating ${
                      position.rating?.startsWith("BBB") ? "mid" : ""
                    }`}
                  >
                    {position.rating || "—"}
                  </span>
                </div>
                <div className="position-meta">
                  {position.isin} · {moneyCompact(position.value_rub)} ·{" "}
                  {pct(position.weight_pct, 1)} портфеля
                </div>
                <div className="weight-bar">
                  <span style={{ width: `${Math.min(position.weight_pct, 100)}%` }} />
                </div>
              </div>
              <div className="position-right">
                <div className="position-value">{pct(position.ytm_pct)}</div>
                <div className="position-sub">
                  дюр. {num(position.duration_years)} г.
                </div>
                <div
                  className="position-sub"
                  style={{
                    color:
                      (position.pnl_rub || 0) >= 0 ? "var(--mint)" : "var(--rose)",
                  }}
                >
                  {(position.pnl_rub || 0) >= 0 ? "+" : ""}
                  {money(position.pnl_rub)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="section two-col">
        <div className="card" style={{ padding: 16 }}>
          <div className="section-head">
            <div>
              <div className="h3">Календарь</div>
              <div className="tiny muted" style={{ marginTop: 4 }}>
                Купоны, оферты и погашения
              </div>
            </div>
            <CalendarDays size={17} style={{ color: "var(--mint)" }} />
          </div>
          <div className="event-list">
            {data.events.slice(0, 5).map((event) => {
              const date = new Date(event.date);
              return (
                <div className="event" key={`${event.isin}-${event.kind}-${event.date}`}>
                  <div className="event-date">
                    <div className="event-day">
                      {date.toLocaleDateString("ru-RU", { day: "2-digit" })}
                    </div>
                    <div className="event-month">
                      {date.toLocaleDateString("ru-RU", { month: "short" })}
                    </div>
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div className="event-title">{event.title}</div>
                    <div className="event-sub">
                      {relativeDays(event.days)} · {event.isin}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="card" style={{ padding: 16 }}>
          <div className="section-head">
            <div>
              <div className="h3">Рейтинги</div>
              <div className="tiny muted" style={{ marginTop: 4 }}>
                Распределение по качеству
              </div>
            </div>
            <ShieldAlert size={17} style={{ color: "var(--gold)" }} />
          </div>
          <RatingBars mix={data.rating_mix} />
          <div className="tiny muted" style={{ marginTop: 4 }}>
            Риск-скор {summary.risk_score}/100 · уровень {summary.risk_level}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <div className="h2">Кандидаты на проверку</div>
            <div className="tiny muted" style={{ marginTop: 4 }}>
              Не рекомендация. Сначала кредитные события и ликвидность
            </div>
          </div>
          <ScanSearch size={17} style={{ color: "var(--mint)" }} />
        </div>

        <div
          className="card"
          style={{
            padding: 14,
            borderColor: "rgba(251,113,133,0.24)",
            background:
              "linear-gradient(180deg, rgba(45,20,24,0.72), rgba(15,27,22,0.86))",
          }}
        >
          <div className="chip rose">
            <ShieldAlert size={12} />
            Риск-гейт включён
          </div>
          <div className="h3" style={{ marginTop: 9 }}>
            Автоматические идеи отключены
          </div>
          <div className="tiny muted" style={{ marginTop: 6, lineHeight: 1.55 }}>
            Система не показывает бумагу как идею, пока не проверены
            кредитные события, аномальная распродажа, ликвидность и свежесть
            котировок. Ниже — бумаги, которые исключены из кандидатов.
          </div>
        </div>

        <div className="candidate-list" style={{ marginTop: 8 }}>
          {data.excluded.map((item) => (
            <div className="candidate" key={item.isin}>
              <div className="candidate-top">
                <div>
                  <div className="position-name">
                    {item.name}
                    <span className={`chip ${item.severity === "blocked" ? "rose" : "gold"}`}>
                      {item.severity === "blocked" ? "Исключён" : "На проверке"}
                    </span>
                  </div>
                  <div className="position-meta">{item.isin}</div>
                </div>
              </div>
              <div className="candidate-reason">{item.reason}</div>
            </div>
          ))}
        </div>

        {data.candidates.length ? (
          <div className="candidate-list" style={{ marginTop: 8 }}>
            {data.candidates.map((candidate) => (
              <div className="candidate" key={candidate.isin}>
                <div className="candidate-top">
                  <div>
                    <div className="position-name">
                      {candidate.name}
                      <span className="rating">{candidate.rating}</span>
                    </div>
                    <div className="position-meta">
                      {candidate.isin} · цена {pct(candidate.price_pct)} · оборот{" "}
                      {num(candidate.volume_mn_rub, 1)} млн ₽
                    </div>
                  </div>
                  <div className="position-right">
                    <div className="position-value">
                      {pct(candidate.ytm_pct)}
                    </div>
                    <div className="position-sub">
                      дюр. {num(candidate.duration_years)} г.
                    </div>
                  </div>
                </div>
                <div className="candidate-reason">{candidate.reason}</div>
                {candidate.risk_flags.length ? (
                  <div className="freelance-meta" style={{ marginTop: 8 }}>
                    {candidate.risk_flags.map((flag) => (
                      <span className="chip rose" key={flag}>
                        {flag}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <section className="section">
        <div className="action-card">
          <div className="action-head">
            <div>
              <div className="chip rose">
                <ShieldAlert size={11} />
                Проверка перед сделкой
              </div>
              <div className="action-title" style={{ marginTop: 9 }}>
                Проверить риск перед заменой
              </div>
            </div>
            <ArrowUpRight size={18} style={{ color: "var(--gold)" }} />
          </div>
          <div className="action-desc">
            Агент не предлагает конкретную бумагу. Он зафиксирует чек-лист
            проверки и покажет, какие кандидаты исключены. Сделка не выставляется.
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={() => onAsk("Предложи замену")}
          >
            Запросить риск-проверку
          </button>
        </div>
      </section>
    </>
  );
}
