import { useEffect, useMemo, useRef, useState } from "react";
import type { ActionRecord, Message, PlanStep, RuntimeState } from "../types";
import { MessageBubble } from "./MessageBubble";
import { Orb } from "./Orb";

const SUGGESTIONS = [
  "Abra o Visual Studio Code",
  "Quanto de RAM estou usando?",
  "Organize minha pasta Downloads",
  "Pesquise sobre inteligência artificial",
  "Quais janelas estão abertas?",
];

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Bom dia";
  if (hour < 18) return "Boa tarde";
  return "Boa noite";
}

export function ChatPanel({
  messages,
  runtime,
  busy,
  voiceBusy,
  pendingActions,
  plan,
  onSend,
  onApprove,
  onListen,
  onCancel,
}: {
  messages: Message[];
  runtime: RuntimeState;
  busy: boolean;
  voiceBusy: boolean;
  pendingActions: ActionRecord[];
  plan: PlanStep[];
  onSend: (text: string) => void;
  onApprove: (actionId: string, approve: boolean) => void;
  onListen: () => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, runtime.state, pendingActions.length]);

  const progress = useMemo(() => {
    if (plan.length === 0) return null;
    const done = plan.filter((step) => step.status === "done").length;
    return { done, total: plan.length };
  }, [plan]);

  const submit = () => {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    onSend(text);
    textareaRef.current?.focus();
  };

  return (
    <main className="chat-panel">
      <div className="chat-scroll">
        {messages.length === 0 ? (
          <div className="welcome">
            <Orb state={runtime.state} detail={runtime.detail} />
            <h1>
              {greeting()}, <span>senhor.</span>
            </h1>
            <p className="welcome-sub">
              Sistemas online. Posso controlar aplicativos, arquivos, processos e o terminal do seu
              Windows — com confirmação para ações sensíveis.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} onClick={() => onSend(suggestion)} disabled={busy}>
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="chat-head">
              <div>
                <div className="chat-kicker">SESSÃO ATIVA</div>
                <div className="chat-title">
                  {progress
                    ? `Plano em execução · ${progress.done}/${progress.total} etapas`
                    : "Diálogo com JARVIS"}
                </div>
              </div>
              <div className={`chat-state state-${runtime.state}`}>
                <span className="status-dot ok" />
                {runtime.detail || runtime.state}
              </div>
            </div>
            <div className="messages">
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
            </div>
          </>
        )}
        {busy || runtime.thinking || runtime.executing ? (
          <div className="thinking-row">
            <span className="thinking-dots">
              <i />
              <i />
              <i />
            </span>
            <span>{runtime.active_tool ? `Executando ${runtime.active_tool}…` : runtime.detail || "Processando…"}</span>
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      {pendingActions.length > 0 ? (
        <div className="confirmation-zone">
          {pendingActions.map((action) => (
            <div className="confirmation-card" key={action.id}>
              <div className="confirmation-head">
                <span className={`level-badge level-${action.permission_level}`}>
                  NÍVEL {action.permission_level}
                </span>
                <span className="confirmation-tool">{action.tool_name}</span>
              </div>
              <div className="confirmation-summary">{action.summary}</div>
              <details className="confirmation-args">
                <summary>Ver argumentos</summary>
                <pre>{JSON.stringify(action.arguments, null, 2)}</pre>
              </details>
              <div className="confirmation-actions">
                <button className="approve" onClick={() => onApprove(action.id, true)} disabled={busy}>
                  Aprovar e executar
                </button>
                <button className="deny" onClick={() => onApprove(action.id, false)} disabled={busy}>
                  Recusar
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="composer-wrap">
        <div className={`composer ${runtime.listening ? "listening" : ""}`}>
          <button
            className={`mic-button ${runtime.listening ? "active" : ""}`}
            onClick={onListen}
            disabled={voiceBusy}
            title="Capturar comando de voz"
          >
            {runtime.listening ? (
              <span className="mic-pulse" />
            ) : null}
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3v10a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v4a3 3 0 0 0 3 3Z" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
            </svg>
          </button>
          <textarea
            ref={textareaRef}
            value={draft}
            placeholder={
              runtime.listening
                ? "Ouvindo… fale seu comando."
                : "Digite um comando ou fale com o JARVIS…"
            }
            rows={1}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            disabled={runtime.listening}
          />
          {busy || runtime.executing || runtime.thinking ? (
            <button className="cancel-button" onClick={onCancel} title="Interromper execução">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              className="send-button"
              onClick={submit}
              disabled={!draft.trim() || busy}
              title="Enviar"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 12l16-8-6 8 6 8-16-8Z" />
              </svg>
            </button>
          )}
        </div>
        <div className="composer-foot">
          <span>ENTER envia · SHIFT+ENTER nova linha</span>
          <span className="secure-note">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7l8-4Z" />
            </svg>
            Ações críticas exigem confirmação
          </span>
        </div>
      </div>
    </main>
  );
}
