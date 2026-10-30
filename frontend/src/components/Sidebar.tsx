import type { Conversation } from "../types";

function formatDate(value: string): string {
  try {
    const date = new Date(value);
    const now = new Date();
    if (date.toDateString() === now.toDateString()) {
      return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    }
    return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  } catch {
    return "";
  }
}

export function Sidebar({
  conversations,
  activeId,
  connected,
  onSelect,
  onNew,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  connected: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <div>
          <div className="sidebar-kicker">ARQUIVO</div>
          <h2>Conversas</h2>
        </div>
        <button className="icon-button new-chat" onClick={onNew} title="Nova conversa">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>
      <div className="conversation-list">
        {conversations.length === 0 ? (
          <div className="empty-hint">
            Nenhuma conversa ainda.
            <br />
            Envie uma mensagem para começar.
          </div>
        ) : (
          conversations.map((conversation) => (
            <button
              key={conversation.id}
              className={`conversation-item ${conversation.id === activeId ? "active" : ""}`}
              onClick={() => onSelect(conversation.id)}
            >
              <div className="conversation-top">
                <span className="conversation-title">{conversation.title}</span>
                <span className="conversation-date">{formatDate(conversation.updated_at)}</span>
              </div>
              <div className="conversation-preview">
                {conversation.last_message || "Sem mensagens"}
              </div>
              <span
                className="conversation-delete"
                role="button"
                tabIndex={0}
                title="Excluir conversa"
                onClick={(event) => {
                  event.stopPropagation();
                  if (window.confirm(`Excluir a conversa “${conversation.title}”?`)) {
                    onDelete(conversation.id);
                  }
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.stopPropagation();
                    if (window.confirm(`Excluir a conversa “${conversation.title}”?`)) {
                      onDelete(conversation.id);
                    }
                  }
                }}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" />
                </svg>
              </span>
            </button>
          ))
        )}
      </div>
      <div className="sidebar-foot">
        <span className={`status-dot ${connected ? "ok" : "fail"}`} />
        <span>{connected ? "LINK EM TEMPO REAL" : "RECONECTANDO…"}</span>
      </div>
    </aside>
  );
}
