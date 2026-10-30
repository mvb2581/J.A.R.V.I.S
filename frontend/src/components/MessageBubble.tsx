import type { Message } from "../types";
import { MarkdownText } from "./MarkdownText";

function formatTime(value: string): string {
  try {
    return new Date(value).toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

interface ToolPayload {
  success?: boolean;
  display?: string | null;
  error?: string | null;
  data?: unknown;
}

function parseToolPayload(content: string): ToolPayload | null {
  try {
    const parsed = JSON.parse(content) as ToolPayload;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function MessageBubble({ message }: { message: Message }) {
  const time = formatTime(message.created_at);

  if (message.role === "tool") {
    const payload = parseToolPayload(message.content);
    const success = payload?.success !== false;
    const summary = payload?.display || payload?.error || "Resultado da ferramenta";
    return (
      <div className={`message tool-message ${success ? "tool-ok" : "tool-fail"}`}>
        <div className="tool-head">
          <span className={`status-dot ${success ? "ok" : "fail"}`} />
          <span className="tool-name">{message.name ?? "ferramenta"}</span>
          <span className="tool-status">{success ? "concluída" : "falhou"}</span>
          <span className="message-time">{time}</span>
        </div>
        <div className="tool-summary">{summary}</div>
        <details className="tool-details">
          <summary>Ver detalhes</summary>
          <pre>
            {payload?.data
              ? JSON.stringify(payload.data, null, 2).slice(0, 6000)
              : message.content.slice(0, 6000)}
          </pre>
        </details>
      </div>
    );
  }

  if (message.role === "assistant" && message.metadata?.kind === "confirmation") {
    return (
      <div className="message assistant-message confirmation-message">
        <div className="message-meta">
          <span className="message-author">JARVIS</span>
          <span className="message-time">{time}</span>
        </div>
        <MarkdownText content={message.content} />
        <div className="confirmation-hint">
          Use os botões de confirmação abaixo ou responda “sim” / “não” (se a confirmação por voz estiver
          habilitada).
        </div>
      </div>
    );
  }

  const hasToolCalls = Boolean(message.tool_calls && message.tool_calls.length > 0);

  return (
    <div className={`message ${message.role === "user" ? "user-message" : "assistant-message"}`}>
      <div className="message-meta">
        <span className="message-author">{message.role === "user" ? "VOCÊ" : "JARVIS"}</span>
        <span className="message-time">{time}</span>
      </div>
      {message.content ? (
        message.role === "user" ? (
          <div className="user-text">{message.content}</div>
        ) : (
          <MarkdownText content={message.content} />
        )
      ) : null}
      {hasToolCalls ? (
        <div className="tool-calls">
          {message.tool_calls?.map((call) => (
            <span className="tool-chip" key={call.id}>
              <span className="pulse-dot" />
              {call.function.name}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
