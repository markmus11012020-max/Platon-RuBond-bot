"use client";

import { AlertTriangle, Plus, RefreshCw, ShieldOff, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { dateRu } from "@/lib/format";
import type { BlocklistEntry, CreditEventEntry } from "@/lib/types";

const TOKEN_KEY = "platon.admin.token";

export function RiskAdmin() {
  const [token, setToken] = useState("");
  const [blocklist, setBlocklist] = useState<BlocklistEntry[]>([]);
  const [events, setEvents] = useState<CreditEventEntry[]>([]);
  const [isin, setIsin] = useState("");
  const [reason, setReason] = useState("");
  const [source, setSource] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    const [blocked, news] = await Promise.allSettled([
      api.riskBlocklist(),
      api.riskEvents(),
    ]);
    if (blocked.status === "fulfilled") setBlocklist(blocked.value);
    if (news.status === "fulfilled") setEvents(news.value);
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
