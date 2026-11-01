"use client";

import {
  Bot,
  BriefcaseBusiness,
  Check,
  ChevronDown,
  LayoutDashboard,
  MessageCircle,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type {
  ActionCard,
  BondOverview,
  Bot as BotType,
  ChatMessage,
  ConfirmResponse,
  FreelanceResponse,
  HealthResponse,
} from "@/lib/types";
import { BondOverviewView } from "@/components/bond-overview";
import { ChatPanel } from "@/components/chat-panel";
import { FreelanceFeed } from "@/components/freelance-feed";
import { BotsView, ProfileView } from "@/components/views";

type Tab = "overview" | "chat" | "bots" | "profile";

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const INITIAL_MESSAGE: ChatMessage = {
  role: "assistant",
  content:
    "Я Bond Copilot. Могу разобрать портфель, риски, купоны и оферты, подобрать замену и подготовить сделку в sandbox.",
};

export function PlatonApp() {
  const [bots, setBots] = useState<BotType[]>([]);
  const [activeBot, setActiveBot] = useState("bond");
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<BondOverview | null>(null);
  const [freelance, setFreelance] = useState<FreelanceResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [installEvent, setInstallEvent] = useState<InstallPromptEvent | null>(
    null,
  );
  const [installDismissed, setInstallDismissed] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_MESSAGE]);
  const [suggestions, setSuggestions] = useState<string[]>([
    "Покажи портфель",
    "Где риск?",
    "Предложи замену",
    "Утренний брифинг",
  ]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [action, setAction] = useState<ActionCard | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const bot = params.get("bot");
    if (bot === "freelance" || bot === "bond") {
      setActiveBot(bot);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .bots()
      .then((items) => {
        if (!cancelled) setBots(items);
      })
      .catch(() => {
        if (!cancelled) setBots([]);
      });
    api
      .health()
      .then((payload) => {
        if (!cancelled) setHealth(payload);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const load =
      activeBot === "bond" ? api.bondOverview() : api.freelanceOrders();
    load
      .then((payload) => {
        if (cancelled) return;
        if (activeBot === "bond") {
          setOverview(payload as BondOverview);
        } else {
          setFreelance(payload as FreelanceResponse);
        }
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setError(exc instanceof Error ? exc.message : "Не удалось загрузить данные");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeBot]);

  useEffect(() => {
    const handler = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as InstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const activeBotMeta = useMemo(
    () => bots.find((item) => item.id === activeBot),
    [activeBot, bots],
  );

  const switchBot = useCallback((botId: string) => {
    setActiveBot(botId);
    setTab("overview");
    setSheetOpen(false);
    const url = new URL(window.location.href);
    url.searchParams.set("bot", botId);
    window.history.replaceState({}, "", url.toString());
  }, []);

  const sendMessage = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || chatLoading) return;
      setMessages((prev) => [...prev, { role: "user", content: text }]);
      setChatInput("");
      setChatLoading(true);
      setAction(null);
      try {
        const response = await api.bondChat(text, messages);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: response.message },
        ]);
        setSuggestions(response.suggestions);
        setAction(response.action);
      } catch (exc) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content:
              exc instanceof Error
                ? `Не удалось получить ответ: ${exc.message}`
                : "Не удалось получить ответ агента.",
          },
        ]);
      } finally {
        setChatLoading(false);
      }
    },
    [chatLoading, messages],
  );

  const openChatWith = useCallback(
    (prompt: string) => {
      setTab("chat");
      void sendMessage(prompt);
    },
    [sendMessage],
  );

  const confirmAction = useCallback(async () => {
    if (!action || confirming) return;
    setConfirming(true);
    try {
      const result: ConfirmResponse = await api.confirmAction(action.id);
      setAction({ ...action, status: "confirmed" });
      const review = action.kind === "review";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `${
            review ? "Риск-проверка зафиксирована." : "Сделка подтверждена в sandbox."
          }\nAudit ID: ${result.audit_id}\n${result.message}`,
        },
      ]);
      setToast(
        `${review ? "Проверка зафиксирована" : "Подтверждено"} · ${result.audit_id}`,
      );
    } catch (exc) {
      setToast(
        exc instanceof Error ? exc.message : "Не удалось подтвердить сделку",
      );
    } finally {
      setConfirming(false);
    }
  }, [action, confirming]);

  const install = async () => {
    if (!installEvent) return;
    await installEvent.prompt();
    const choice = await installEvent.userChoice;
    if (choice.outcome === "accepted") {
      setInstallDismissed(true);
      setToast("Platon установлен на устройство");
    }
    setInstallEvent(null);
  };

  const bottomItems: { id: Tab; label: string; icon: typeof LayoutDashboard }[] =
    activeBot === "bond"
      ? [
          { id: "overview", label: "Обзор", icon: LayoutDashboard },
          { id: "chat", label: "Агент", icon: MessageCircle },
          { id: "bots", label: "Боты", icon: Bot },
          { id: "profile", label: "Ещё", icon: Settings2 },
        ]
      : [
          { id: "overview", label: "Лента", icon: BriefcaseBusiness },
          { id: "bots", label: "Боты", icon: Bot },
          { id: "profile", label: "Ещё", icon: Settings2 },
        ];

  return (
    <div className="app-shell">
      <div className="ambient" />

      <header className="app-header">
        <div className="app-container">
          <div className="header-row">
            <div className="brand">
              <div className="brand-mark">P</div>
              <div className="brand-copy">
                <div className="brand-name">Platon</div>
                <div className="brand-sub">
                  {activeBotMeta?.tagline || "инвестиционный Copilot"}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button
                type="button"
                className="bot-switcher"
                onClick={() => setSheetOpen(true)}
              >
                <span className="bot-dot">
                  {activeBot === "bond" ? (
                    <Sparkles size={12} />
                  ) : (
                    <BriefcaseBusiness size={12} />
                  )}
                </span>
                <span className="bot-switcher-label bot-label-full">
                  {activeBotMeta?.name || "Bond Copilot"}
                </span>
                <span className="bot-switcher-label bot-label-short">
                  {activeBot === "bond" ? "Bond" : "Freelance"}
                </span>
                <ChevronDown size={13} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label="Настройки"
                onClick={() => setTab("profile")}
              >
                <Settings2 size={18} />
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="app-container">
        <div className="app-grid">
          <aside className="desktop-sidebar">
            <div className="sidebar-label">Мои боты</div>
            {(bots.length ? bots : FALLBACK_BOTS).map((bot) => (
              <button
                key={bot.id}
                type="button"
                className={`sidebar-item ${activeBot === bot.id ? "active" : ""}`}
                onClick={() => switchBot(bot.id)}
              >
                <Bot size={15} />
                <span style={{ flex: 1 }}>{bot.name}</span>
                <StatusDot status={bot.status} />
              </button>
            ))}
            <div className="sidebar-label" style={{ marginTop: 10 }}>
              Навигация
            </div>
            {bottomItems.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`sidebar-item ${tab === item.id ? "active" : ""}`}
                  onClick={() => setTab(item.id)}
                >
                  <Icon size={15} />
                  {item.label}
                </button>
              );
            })}
            <div
              style={{
                marginTop: 14,
                padding: 12,
                borderRadius: 16,
                border: "1px solid var(--line)",
                background: "rgba(7,17,15,0.4)",
              }}
            >
              <div className="tiny muted">Режим данных</div>
              <div style={{ marginTop: 4, fontSize: 12, fontWeight: 700 }}>
                {health?.mcp_ready
                  ? "T-Invest MCP подключён"
                  : health?.demo_mode
                    ? "Demo + sandbox"
                    : "Локальные данные"}
              </div>
              <div className="tiny muted" style={{ marginTop: 4 }}>
                {health?.mcp_mode === "prod" ? "production" : "sandbox"} ·{" "}
                {health?.mcp_ready ? "read-only" : "mock"}
              </div>
            </div>
          </aside>

          <main className="page">
            {error ? (
              <div className="empty" style={{ marginTop: 18 }}>
                {error}
                <div style={{ marginTop: 12 }}>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => window.location.reload()}
                  >
                    Повторить
                  </button>
                </div>
              </div>
            ) : null}

            {tab === "overview" && activeBot === "bond" ? (
              loading || !overview ? (
                <OverviewSkeleton />
              ) : (
                <BondOverviewView
                  data={overview}
                  onAsk={openChatWith}
                  onOpenChat={() => setTab("chat")}
                />
              )
            ) : null}

            {tab === "overview" && activeBot === "freelance" ? (
              loading || !freelance ? (
                <FreelanceSkeleton />
              ) : (
                <FreelanceFeed data={freelance} />
              )
            ) : null}

            {tab === "chat" && activeBot === "bond" ? (
              <ChatPanel
                messages={messages}
                suggestions={suggestions}
                input={chatInput}
                loading={chatLoading}
                action={action}
                confirming={confirming}
                onInput={setChatInput}
                onSend={() => void sendMessage(chatInput)}
                onSuggestion={(value) => void sendMessage(value)}
                onConfirm={() => void confirmAction()}
              />
            ) : null}

            {tab === "bots" ? (
              <BotsView
                bots={bots.length ? bots : FALLBACK_BOTS}
                activeBot={activeBot}
                onSelect={switchBot}
              />
            ) : null}

            {tab === "profile" ? (
              <ProfileView
                health={health}
                onInstall={() => void install()}
                canInstall={Boolean(installEvent) && !installDismissed}
              />
            ) : null}
          </main>

          <aside className="desktop-rail">
            <div className="card" style={{ padding: 14 }}>
              <div className="eyebrow">
                <span className="eyebrow-dot" />
                Быстрый вопрос
              </div>
              <div className="h3" style={{ marginTop: 8 }}>
                Что сделать с портфелем?
              </div>
              <div className="tiny muted" style={{ marginTop: 6 }}>
                Агент ответит на основе портфеля, MCP и локальной аналитики.
              </div>
              <div style={{ display: "grid", gap: 7, marginTop: 12 }}>
                {[
                  "Где риск?",
                  "Предложи замену",
                  "Что с купонами?",
                  "Утренний брифинг",
                ].map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    className="secondary-button"
                    style={{ textAlign: "left" }}
                    onClick={() => openChatWith(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
              <div
                style={{
                  marginTop: 14,
                  paddingTop: 12,
                  borderTop: "1px solid var(--line)",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <ShieldCheck size={15} style={{ color: "var(--mint)" }} />
                <div className="tiny muted">
                  HITL: сделка только после подтверждения
                </div>
              </div>
            </div>
          </aside>
        </div>
      </div>

      <nav
        className="bottom-nav"
        style={{
          gridTemplateColumns: `repeat(${bottomItems.length}, 1fr)`,
        }}
      >
        {bottomItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              className={`nav-item ${tab === item.id ? "active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              <Icon />
              {item.label}
            </button>
          );
        })}
      </nav>

      {sheetOpen ? (
        <div
          className="sheet-backdrop"
          onClick={() => setSheetOpen(false)}
          role="presentation"
        >
          <div
            className="sheet"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Выбор бота"
          >
            <div className="sheet-handle" />
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 12,
              }}
            >
              <div>
                <div className="h2">Мои боты</div>
                <div className="tiny muted" style={{ marginTop: 4 }}>
                  Один аккаунт, общие пуши и дизайн
                </div>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setSheetOpen(false)}
                aria-label="Закрыть"
              >
                <X size={17} />
              </button>
            </div>
            <div className="bot-grid">
              {(bots.length ? bots : FALLBACK_BOTS).map((bot) => (
                <button
                  key={bot.id}
                  type="button"
                  className={`bot-card ${activeBot === bot.id ? "active" : ""}`}
                  onClick={() => switchBot(bot.id)}
                >
                  <span
                    className={`bot-icon ${bot.id === "freelance" ? "gold" : ""}`}
                  >
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
                  ) : null}
                </button>
              ))}
            </div>
            <div className="empty" style={{ marginTop: 12 }}>
              Следующий модуль: мониторинг новостей и алерты.
            </div>
          </div>
        </div>
      ) : null}

      {toast ? <div className="toast">{toast}</div> : null}
    </div>
  );
}

function StatusDot({ status }: { status: BotType["status"] }) {
  const color =
    status === "live" ? "var(--mint)" : status === "beta" ? "var(--gold)" : "var(--muted-2)";
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: 999,
        background: color,
        boxShadow: status === "live" ? "0 0 10px rgba(56,217,169,.7)" : "none",
      }}
    />
  );
}

function OverviewSkeleton() {
  return (
    <div style={{ display: "grid", gap: 12, marginTop: 18 }}>
      <div className="skeleton" style={{ height: 240 }} />
      <div className="skeleton" style={{ height: 180 }} />
      <div className="skeleton" style={{ height: 260 }} />
    </div>
  );
}

function FreelanceSkeleton() {
  return (
    <div style={{ display: "grid", gap: 10, marginTop: 18 }}>
      <div className="skeleton" style={{ height: 120 }} />
      {[0, 1, 2].map((item) => (
        <div key={item} className="skeleton" style={{ height: 130 }} />
      ))}
    </div>
  );
}

const FALLBACK_BOTS: BotType[] = [
  {
    id: "bond",
    name: "Bond Copilot",
    tagline: "AI-агент для облигационного портфеля",
    icon: "bond",
    status: "live",
    accent: "#38d9a9",
    features: ["Портфель", "Сделки", "Купоны", "Риск"],
  },
  {
    id: "freelance",
    name: "Freelance Radar",
    tagline: "Заказы и проекты в одном потоке",
    icon: "briefcase",
    status: "beta",
    accent: "#f6c453",
    features: ["Заказы", "Скор", "Бюджеты"],
  },
];
