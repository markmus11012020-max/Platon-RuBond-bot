"use client";

import {
  ArrowUpRight,
  BriefcaseBusiness,
  CircleDollarSign,
  Filter,
  Flame,
  Hash,
  ShieldAlert,
} from "lucide-react";

import { dateRu } from "@/lib/format";
import type { FreelanceResponse } from "@/lib/types";

export function FreelanceFeed({ data }: { data: FreelanceResponse }) {
  return (
    <>
      <section className="card hero" style={{ marginTop: 14 }}>
        <div className="hero-top">
          <div>
            <div className="eyebrow">
              <span className="eyebrow-dot" />
              Freelance Radar · beta
            </div>
            <div className="metric-label" style={{ marginTop: 14 }}>
              Заказов в ленте
            </div>
            <div className="metric-value">{data.summary.count}</div>
            <div className="pnl">
              <Flame size={13} />
              Лучший скор {data.summary.top_score}/100
            </div>
          </div>
          <span className="bot-icon gold" style={{ width: 44, height: 44 }}>
            <BriefcaseBusiness size={20} />
          </span>
        </div>
        <div className="hero-grid">
          <div className="stat">
            <div className="metric-label">Источник</div>
            <div className="stat-value">
              {data.summary.source === "sqlite" ? "SQLite" : "Demo"}
            </div>
          </div>
          <div className="stat">
            <div className="metric-label">Фильтр</div>
            <div className="stat-value">AI / Python</div>
          </div>
          <div className="stat">
            <div className="metric-label">Режим</div>
            <div className="stat-value">read-only</div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <div className="h2">Лента заказов</div>
            <div className="tiny muted" style={{ marginTop: 4 }}>
              Отсортировано по скору и свежести
            </div>
          </div>
          <div className="chip">
            <Filter size={12} />
            Все
          </div>
        </div>
        <div className="freelance-list">
          {data.orders.map((order) => (
            <article className="freelance-card" key={order.id}>
              <div className="freelance-top">
                <div style={{ minWidth: 0 }}>
                  <div className="freelance-title">{order.title}</div>
                  <div className="freelance-meta">
                    <span className="chip">{order.source}</span>
                    {order.category ? (
                      <span className="chip">
                        <Hash size={10} />
                        {order.category}
                      </span>
                    ) : null}
                    {order.published_at ? (
                      <span className="chip">{dateRu(order.published_at)}</span>
                    ) : null}
                  </div>
                </div>
                <div className="score">{order.score}</div>
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                  marginTop: 12,
                }}
              >
                <div className="freelance-budget">
                  <CircleDollarSign size={13} style={{ marginRight: 4 }} />
                  {order.budget_text || "Бюджет не указан"}
                </div>
                <a
                  className="secondary-button"
                  href={order.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                >
                  Открыть
                  <ArrowUpRight size={13} />
                </a>
              </div>

              {order.matched_keywords.length ? (
                <div className="freelance-meta" style={{ marginTop: 10 }}>
                  {order.matched_keywords.slice(0, 5).map((keyword) => (
                    <span className="chip mint" key={keyword}>
                      {keyword}
                    </span>
                  ))}
                </div>
              ) : null}

              {order.red_flags.length ? (
                <div
                  className="tiny"
                  style={{
                    marginTop: 10,
                    color: "#fecdd3",
                    display: "flex",
                    gap: 6,
                    alignItems: "flex-start",
                  }}
                >
                  <ShieldAlert size={13} style={{ flex: "0 0 auto", marginTop: 1 }} />
                  {order.red_flags.join(" · ")}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="card" style={{ padding: 16 }}>
          <div className="h3">Как это связано с Platon</div>
          <div className="tiny muted" style={{ marginTop: 7, lineHeight: 1.55 }}>
            Freelance Radar — второй модуль платформы. Он использует общий дизайн,
            навигацию и авторизацию, но читает собственную базу заказов. Так
            добавляются новые боты без переписывания приложения.
          </div>
        </div>
      </section>
    </>
  );
}
