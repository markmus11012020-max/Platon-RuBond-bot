"use client";

import {
  ArrowRight,
  Bot,
  BriefcaseBusiness,
  Check,
  Download,
  ExternalLink,
  Server,
  ShieldCheck,
  Sparkles,
  Wifi,
} from "lucide-react";

import type { Bot as BotType, HealthResponse } from "@/lib/types";

export function BotsView({
  bots,
  activeBot,
  onSelect,
}: {
  bots: BotType[];
  activeBot: string;
  onSelect: (id: string) => void;
}) {
  return (
    <>
      <div className="section-head" style={{ marginTop: 12 }}>
        <div>
          <div className="eyebrow">
            <span className="eyebrow-dot" />
            Платформа
          </div>
          <h1 className="h1" style={{ fontSize: 32 }}>
            Мои боты
          </h1>
        </div>
        <div className="chip mint">
          <Bot size={12} />
          {bots.length}
        </div>
      </div>

      <div className="bot-grid">
        {bots.map((bot) => (
          <button
            key={bot.id}
            type="button"
            className={`bot-card ${activeBot === bot.id ? "active" : ""}`}
            onClick={() => onSelect(bot.id)}
          >
            <span className={`bot-icon ${bot.id === "freelance" ? "gold" : ""}`}>
              {bot.id === "freelance" ? (
                <BriefcaseBusiness size={20} />
              ) : (
                <Sparkles size={20} />
              )}
            </span>
            <span className="bot-copy">
              <span className="bot-name">{bot.name}</span>
              <span className="bot-tagline">{bot.tagline}</span>
              <span className="bot-features">
                {bot.features.map((feature) => (
                  <span className="bot-feature" key={feature}>
                    {feature}
                  </span>
                ))}
              </span>
            </span>
            {activeBot === bot.id ? (
              <Check size={16} style={{ color: "var(--mint)" }} />
            ) : (
              <ArrowRight size={16} style={{ color: "var(--muted-2)" }} />
            )}
          </button>
        ))}
      </div>

      <section className="section">
        <div className="card" style={{ padding: 16 }}>
          <div className="h3">Добавить бота</div>
          <div className="tiny muted" style={{ marginTop: 7, lineHeight: 1.55 }}>
            Новый модуль получает манифест, API-prefix и собственную БД. Общие
            авторизация, пуши и дизайн остаются на платформе.
          </div>
          <div className="bot-features" style={{ marginTop: 12 }}>
            <span className="bot-feature">манифест</span>
            <span className="bot-feature">API gateway</span>
            <span className="bot-feature">PWA</span>
            <span className="bot-feature">push</span>
          </div>
        </div>
      </section>
    </>
  );
}

export function ProfileView({
  health,
  onInstall,
  canInstall,
}: {
  health: HealthResponse | null;
  onInstall: () => void;
  canInstall: boolean;
}) {
  const mcpText = health?.mcp_ready
    ? "подключён"
    : health?.mcp_enabled
      ? "токен не задан"
      : "выключен";
  return (
    <>
      <div className="section-head" style={{ marginTop: 12 }}>
        <div>
          <div className="eyebrow">
            <span className="eyebrow-dot" />
            Настройки
          </div>
          <h1 className="h1" style={{ fontSize: 32 }}>
            Ещё
          </h1>
        </div>
        <div className="chip">
          <Server size={12} />
          {health?.environment || "dev"}
        </div>
      </div>

      <section className="card" style={{ padding: 16 }}>
        <div className="h3">Состояние системы</div>
        <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
          <StatusRow
            icon={<Wifi size={14} />}
            label="API"
            value={health?.status === "ok" ? "онлайн" : "нет связи"}
            good={health?.status === "ok"}
          />
          <StatusRow
            icon={<Sparkles size={14} />}
            label="T-Invest MCP"
            value={mcpText}
            good={Boolean(health?.mcp_ready)}
          />
          <StatusRow
            icon={<ShieldCheck size={14} />}
            label="Режим"
            value={health?.demo_mode ? "demo / sandbox" : "production"}
            good
          />
          <StatusRow
            icon={<BriefcaseBusiness size={14} />}
            label="Freelance DB"
            value={health?.freelance_db ? "подключена" : "demo"}
            good={Boolean(health?.freelance_db)}
          />
        </div>
      </section>

      <section className="section card" style={{ padding: 16 }}>
        <div className="h3">Приложение</div>
        <div className="tiny muted" style={{ marginTop: 7, lineHeight: 1.55 }}>
          Platon — PWA. Устанавливается на телефон, работает в standalone-режиме,
          хранит общий дизайн и навигацию для всех ботов.
        </div>
        <button
          type="button"
          className="primary-button"
          onClick={onInstall}
          disabled={!canInstall}
          style={{ marginTop: 12 }}
        >
          <span
            style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
          >
            <Download size={15} />
            {canInstall ? "Установить Platon" : "Установка из меню браузера"}
          </span>
        </button>
      </section>

      <section className="section card" style={{ padding: 16 }}>
        <div className="h3">Документация</div>
        <div className="tiny muted" style={{ marginTop: 7, lineHeight: 1.55 }}>
          API: /api/docs. MCP: T-Invest sandbox. Сделки выполняются только после
          подтверждения, токены не попадают в браузер.
        </div>
        <a
          className="secondary-button"
          href="/api/docs"
          target="_blank"
          rel="noreferrer noopener"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            marginTop: 12,
          }}
        >
          Открыть API
          <ExternalLink size={13} />
        </a>
      </section>
    </>
  );
}

function StatusRow({
  icon,
  label,
  value,
  good,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  good: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        padding: "10px 12px",
        border: "1px solid var(--line)",
        borderRadius: 14,
        background: "rgba(7,17,15,0.35)",
      }}
    >
      <span style={{ color: good ? "var(--mint)" : "var(--muted-2)" }}>
        {icon}
      </span>
      <span style={{ flex: 1, fontSize: 12, color: "var(--muted)" }}>
        {label}
      </span>
      <span style={{ fontSize: 11.5, fontWeight: 700 }}>{value}</span>
    </div>
  );
}
