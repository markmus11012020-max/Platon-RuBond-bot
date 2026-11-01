"use client";

import { ArrowUp, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useRef } from "react";

import { ActionCardView } from "@/components/action-card";
import type { ActionCard, ChatMessage } from "@/lib/types";

export function ChatPanel({
  messages,
  suggestions,
  input,
  loading,
  action,
  confirming,
  onInput,
  onSend,
  onSuggestion,
  onConfirm,
}: {
  messages: ChatMessage[];
  suggestions: string[];
  input: string;
  loading: boolean;
  action: ActionCard | null;
  confirming: boolean;
  onInput: (value: string) => void;
  onSend: () => void;
  onSuggestion: (value: string) => void;
  onConfirm: () => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, loading, action]);

  return (
    <div className="chat-shell">
      <div className="section-head" style={{ marginTop: 8 }}>
        <div>
          <div className="eyebrow">
            <span className="eyebrow-dot" />
            Bond Copilot · sandbox
          </div>
          <h1 className="h1" style={{ fontSize: 30 }}>
            Агент
          </h1>
        </div>
        <div className="chip mint">
          <ShieldCheck size={12} />
          HITL
        </div>
      </div>

      <div className="chat-scroll">
        {messages.map((message, index) => (
          <div
            className={`message ${message.role}`}
            key={`${message.role}-${index}`}
          >
            {message.content}
          </div>
        ))}
        {loading ? (
          <div className="message assistant">
            <span className="typing">
              <span />
              <span />
              <span />
            </span>
          </div>
        ) : null}
        {action ? (
          <div style={{ marginTop: 4, width: "100%" }}>
            <ActionCardView
              action={action}
              onConfirm={onConfirm}
              confirming={confirming}
            />
          </div>
        ) : null}
        <div ref={endRef} />
      </div>

      {suggestions.length ? (
        <div className="suggestions">
          {suggestions.slice(0, 5).map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              className="suggestion"
              onClick={() => onSuggestion(suggestion)}
              disabled={loading}
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}

      <div className="composer">
        <textarea
          rows={1}
          value={input}
          placeholder="Спроси про портфель, риск, купоны или замену..."
          onChange={(event) => onInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
        />
        <button
          type="button"
          className="send-button"
          onClick={onSend}
          disabled={!input.trim() || loading}
          aria-label="Отправить"
        >
          <ArrowUp size={18} />
        </button>
      </div>

      <div
        className="tiny muted"
        style={{
          display: "flex",
          gap: 6,
          alignItems: "center",
          justifyContent: "center",
          padding: "10px 0 4px",
        }}
      >
        <Sparkles size={11} />
        Числа считает код, LLM объясняет. Не индивидуальная инвестиционная
        рекомендация.
      </div>
    </div>
  );
}
