"use client";

import { AlertTriangle, Plus, RefreshCw, ShieldOff, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { dateRu } from "@/lib/format";
import type { BlocklistEntry, CreditEventEntry, FundamentalsEntry } from "@/lib/types";

const TOKEN_KEY = "platon.admin.token";

const EMPTY_FUND = {
  isin: "",
  issuer: "",
  period: "",
  revenue: "",
  profit: "",
  ebitda: "",
  debt: "",
  equity: "",
  ratio: "",
  source: "",
  sourceUrl: "",
  notes: "",
};

export function RiskAdmin() {
  const [token, setToken] = useState("");
  const [blocklist, setBlocklist] = useState<BlocklistEntry[]>([]);
  const [events, setEvents] = useState<CreditEventEntry[]>([]);
  const [fundamentals, setFundamentals] = useState<FundamentalsEntry[]>([]);
  const [isin, setIsin] = useState("");
  const [reason, setReason] = useState("");
  const [source, setSource] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [fund, setFund] = useState(EMPTY_FUND);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    const [blocked, news, reports] = await Promise.allSettled([
      api.riskBlocklist(),
      api.riskEvents(),
      api.riskFundamentals(),
    ]);
    if (blocked.status === "fulfilled") setBlocklist(blocked.value);
    if (news.status === "fulfilled") setEvents(news.value);
    if (reports.status === "fulfilled") setFundamentals(reports.value);
  };

  useEffect(() => {
    const saved = window.sessionStorage.getItem(TOKEN_KEY) || "";
    setToken(saved);
    void refresh();
  }, []);

  const rememberToken = (value: string) => {
    setToken(value);
    window.sessionStorage.setItem(TOKEN_KEY, value);
  };

  const add = async () => {
    if (!isin.trim() || !reason.trim() || !source.trim()) {
      setMessage("Нужны ISIN, причина и источник.");
      return;
    }
    if (!token) {
      setMessage("Введи admin token из .env.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      await api.addRiskBlocklist(token, {
        isin: isin.trim(),
        reason: reason.trim(),
        source: source.trim(),
        source_url: sourceUrl.trim(),
      });
      setIsin("");
      setReason("");
      setSource("");
      setSourceUrl("");
      setMessage("Бумага добавлена в блоклист.");
      await refresh();
    } catch (exc) {
      setMessage(exc instanceof Error ? exc.message : "Не удалось добавить");
    } finally {
      setLoading(false);
    }
  };

  const remove = async (value: string) => {
    if (!token) {
      setMessage("Введи admin token из .env.");
      return;
    }
    setLoading(true);
    try {
      await api.deleteRiskBlocklist(token, value);
      setMessage(`${value} удалён из блоклиста.`);
      await refresh();
    } catch (exc) {
      setMessage(exc instanceof Error ? exc.message : "Не удалось удалить");
    } finally {
      setLoading(false);
    }
  };

  const addFundamentals = async () => {
    if (!fund.isin.trim() && !fund.issuer.trim()) {
      setMessage("Для фундаментала нужен ISIN или эмитент.");
      return;
    }
    if (!fund.period.trim() || !fund.source.trim()) {
      setMessage("Нужны период и источник.");
      return;
    }
    if (!token) {
      setMessage("Введи admin token из .env.");
      return;
    }
    const number = (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) return null;
      const parsed = Number(trimmed.replace(",", "."));
      return Number.isFinite(parsed) ? parsed : null;
    };
    setLoading(true);
    setMessage("");
    try {
      await api.addRiskFundamentals(token, {
        isin: fund.isin.trim(),
        issuer: fund.issuer.trim(),
        period: fund.period.trim(),
        revenue_rub: number(fund.revenue),
        net_profit_rub: number(fund.profit),
        ebitda_rub: number(fund.ebitda),
        net_debt_rub: number(fund.debt),
        equity_rub: number(fund.equity),
        current_ratio: number(fund.ratio),
        source: fund.source.trim(),
        source_url: fund.sourceUrl.trim(),
        notes: fund.notes.trim(),
      });
      setFund(EMPTY_FUND);
      setMessage("Фундаментал сохранён. Агент увидит его в следующем ответе.");
      await refresh();
    } catch (exc) {
      setMessage(exc instanceof Error ? exc.message : "Не удалось сохранить фундаментал");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="section card" style={{ padding: 16 }}>
      <div className="section-head" style={{ marginBottom: 8 }}>
        <div>
          <div className="eyebrow">
            <span className="eyebrow-dot" />
            Risk Admin
          </div>
          <div className="h3" style={{ marginTop: 6 }}>
            Блоклист и кредитные события
          </div>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={() => void refresh()}
          aria-label="Обновить"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      <div className="tiny muted" style={{ lineHeight: 1.5 }}>
        Ручной блоклист — обязательный слой перед любыми идеями. Токен хранится
        только в sessionStorage и не попадает в публичные ответы API.
      </div>

      <div className="field" style={{ marginTop: 12 }}>
        <label className="field-label" htmlFor="risk-token">
          Admin token
        </label>
        <input
          id="risk-token"
          className="input"
          type="password"
          value={token}
          onChange={(event) => rememberToken(event.target.value)}
          placeholder="PREMARKET_ADMIN_TOKEN"
          autoComplete="off"
        />
      </div>

      <div className="admin-grid">
        <div className="field">
          <label className="field-label" htmlFor="risk-isin">
            ISIN
          </label>
          <input
            id="risk-isin"
            className="input"
            value={isin}
            onChange={(event) => setIsin(event.target.value.toUpperCase())}
            placeholder="RU000A10G1Q1"
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="risk-reason">
            Причина
          </label>
          <input
            id="risk-reason"
            className="input"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Технический дефолт"
          />
        </div>
      </div>

      <div className="admin-grid">
        <div className="field">
          <label className="field-label" htmlFor="risk-source">
            Источник
          </label>
          <input
            id="risk-source"
            className="input"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            placeholder="Название источника"
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="risk-source-url">
            Ссылка на источник
          </label>
          <input
            id="risk-source-url"
            className="input"
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="https://..."
          />
        </div>
      </div>

      <button
        type="button"
        className="primary-button"
        onClick={() => void add()}
        disabled={loading}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
          <Plus size={15} />
          {loading ? "Сохраняю..." : "Добавить в блоклист"}
        </span>
      </button>

      {message ? (
        <div className="tiny" style={{ marginTop: 10, color: "var(--mint-soft)" }}>
          {message}
        </div>
      ) : null}

      <div style={{ marginTop: 16 }}>
        <div className="h3">Активный блоклист</div>
        <div style={{ display: "grid", gap: 7, marginTop: 8 }}>
          {blocklist.length ? (
            blocklist.map((item) => (
              <div className="admin-row" key={item.isin}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 750, fontSize: 12 }}>
                    {item.isin}
                  </div>
                  <div className="tiny muted" style={{ marginTop: 3 }}>
                    {item.reason}
                  </div>
                  <div className="tiny" style={{ marginTop: 3, color: "var(--muted-2)" }}>
                    {item.source} · {dateRu(item.added_at)}
                  </div>
                </div>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => void remove(item.isin)}
                  aria-label={`Удалить ${item.isin}`}
                  style={{ width: 34, height: 34, flex: "0 0 auto" }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          ) : (
            <div className="tiny muted">Блоклист пуст.</div>
          )}
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <div className="h3">Фундаментал эмитента</div>
        <div className="tiny muted" style={{ marginTop: 5, lineHeight: 1.5 }}>
          Только проверенные данные из отчётности или официального источника.
          Суммы указывай в рублях. Если поле пустое — агент увидит «нет данных».
        </div>

        <div className="admin-grid">
          <div className="field">
            <label className="field-label" htmlFor="fund-isin">
              ISIN
            </label>
            <input
              id="fund-isin"
              className="input"
              value={fund.isin}
              onChange={(event) =>
                setFund({ ...fund, isin: event.target.value.toUpperCase() })
              }
              placeholder="RU000A10E4Y1"
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="fund-issuer">
              Эмитент
            </label>
            <input
              id="fund-issuer"
              className="input"
              value={fund.issuer}
              onChange={(event) => setFund({ ...fund, issuer: event.target.value })}
              placeholder="Аэрофьюэлз"
            />
          </div>
        </div>

        <div className="admin-grid">
          <div className="field">
            <label className="field-label" htmlFor="fund-period">
              Период
            </label>
            <input
              id="fund-period"
              className="input"
              value={fund.period}
              onChange={(event) => setFund({ ...fund, period: event.target.value })}
              placeholder="2025FY"
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="fund-source">
              Источник
            </label>
            <input
              id="fund-source"
              className="input"
              value={fund.source}
              onChange={(event) => setFund({ ...fund, source: event.target.value })}
              placeholder="e-disclosure / МСФО"
            />
          </div>
        </div>

        <div className="admin-grid">
          <div className="field">
            <label className="field-label" htmlFor="fund-revenue">
              Выручка, ₽
            </label>
            <input
              id="fund-revenue"
              className="input"
              inputMode="decimal"
              value={fund.revenue}
              onChange={(event) => setFund({ ...fund, revenue: event.target.value })}
              placeholder="12500000000"
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="fund-profit">
              Чистая прибыль, ₽
            </label>
            <input
              id="fund-profit"
              className="input"
              inputMode="decimal"
              value={fund.profit}
              onChange={(event) => setFund({ ...fund, profit: event.target.value })}
              placeholder="1200000000"
            />
          </div>
        </div>

        <div className="admin-grid">
          <div className="field">
            <label className="field-label" htmlFor="fund-ebitda">
              EBITDA, ₽
            </label>
            <input
              id="fund-ebitda"
              className="input"
              inputMode="decimal"
              value={fund.ebitda}
              onChange={(event) => setFund({ ...fund, ebitda: event.target.value })}
              placeholder="2100000000"
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="fund-debt">
              Чистый долг, ₽
            </label>
            <input
              id="fund-debt"
              className="input"
              inputMode="decimal"
              value={fund.debt}
              onChange={(event) => setFund({ ...fund, debt: event.target.value })}
              placeholder="3400000000"
            />
          </div>
        </div>

        <div className="admin-grid">
          <div className="field">
            <label className="field-label" htmlFor="fund-equity">
              Капитал, ₽
            </label>
            <input
              id="fund-equity"
              className="input"
              inputMode="decimal"
              value={fund.equity}
              onChange={(event) => setFund({ ...fund, equity: event.target.value })}
              placeholder="5000000000"
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="fund-ratio">
              Current ratio
            </label>
            <input
              id="fund-ratio"
              className="input"
              inputMode="decimal"
              value={fund.ratio}
              onChange={(event) => setFund({ ...fund, ratio: event.target.value })}
              placeholder="1.4"
            />
          </div>
        </div>

        <div className="field" style={{ marginTop: 10 }}>
          <label className="field-label" htmlFor="fund-source-url">
            Ссылка на источник
          </label>
          <input
            id="fund-source-url"
            className="input"
            value={fund.sourceUrl}
            onChange={(event) => setFund({ ...fund, sourceUrl: event.target.value })}
            placeholder="https://www.e-disclosure.ru/..."
          />
        </div>

        <button
          type="button"
          className="primary-button"
          onClick={() => void addFundamentals()}
          disabled={loading}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
            <Plus size={15} />
            {loading ? "Сохраняю..." : "Сохранить фундаментал"}
          </span>
        </button>

        <div style={{ display: "grid", gap: 7, marginTop: 10 }}>
          {fundamentals.length ? (
            fundamentals.slice(0, 6).map((item) => (
              <div className="admin-row" key={`${item.isin}-${item.issuer}-${item.period}-${item.source}`}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 750, fontSize: 12 }}>
                    {item.isin || item.issuer} · {item.period}
                  </div>
                  <div className="tiny muted" style={{ marginTop: 3 }}>
                    {item.revenue_rub !== null
                      ? `Выручка ${(item.revenue_rub / 1_000_000).toFixed(1)} млн ₽`
                      : "Выручка: нет данных"}
                    {item.ebitda_rub !== null
                      ? ` · EBITDA ${(item.ebitda_rub / 1_000_000).toFixed(1)} млн ₽`
                      : ""}
                    {item.net_debt_rub !== null
                      ? ` · Долг ${(item.net_debt_rub / 1_000_000).toFixed(1)} млн ₽`
                      : ""}
                  </div>
                  <div className="tiny" style={{ marginTop: 3, color: "var(--muted-2)" }}>
                    {item.source} · {dateRu(item.updated_at)}
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="tiny muted">Фундаментал пока не загружен.</div>
          )}
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <div className="h3">Кредитные события</div>
        <div style={{ display: "grid", gap: 7, marginTop: 8 }}>
          {events.length ? (
            events.slice(0, 8).map((item) => (
              <div className="admin-row" key={`${item.isin}-${item.event_date}`}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 750, fontSize: 12 }}>
                    {item.isin} · {item.event_type}
                  </div>
                  <div className="tiny muted" style={{ marginTop: 3 }}>
                    {item.summary}
                  </div>
                  <div className="tiny" style={{ marginTop: 3, color: "var(--muted-2)" }}>
                    {item.source} · {dateRu(item.event_date)}
                  </div>
                </div>
                <ShieldOff size={15} style={{ color: "var(--rose)", flex: "0 0 auto" }} />
              </div>
            ))
          ) : (
            <div className="tiny muted">Кредитных событий нет.</div>
          )}
        </div>
      </div>

      <div className="tiny" style={{ marginTop: 12, color: "var(--muted-2)", display: "flex", gap: 6 }}>
        <AlertTriangle size={13} style={{ flex: "0 0 auto", marginTop: 1 }} />
        Демо-записи помечены source=manual/demo. Для production нужен реальный
        источник и дата проверки.
      </div>
    </section>
  );
}
