import { useMemo, useState } from "react";
import type { ActionRecord, ActionStatus } from "../types";

const STATUS_LABEL: Record<ActionStatus, string> = {
  pending: "Aguardando",
  executing: "Executando",
  executed: "Executada",
  failed: "Falhou",
  denied: "Recusada",
  blocked: "Bloqueada",
};

const FILTERS: Array<{ id: "all" | ActionStatus; label: string }> = [
  { id: "all", label: "Todas" },
  { id: "executed", label: "Executadas" },
  { id: "pending", label: "Pendentes" },
  { id: "failed", label: "Falhas" },
  { id: "blocked", label: "Bloqueadas" },
];

function formatTime(value: string): string {
  try {
    return new Date(value).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return value;
  }
}

function duration(action: ActionRecord): string {
  if (!action.completed_at) return "—";
  try {
    const start = new Date(action.created_at).getTime();
    const end = new Date(action.completed_at).getTime();
    const seconds = Math.max(0, (end - start) / 1000);
    if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
    return `${seconds.toFixed(1)} s`;
  } catch {
    return "—";
  }
}

export function ActionsPanel({
  actions,
  activeConversation,
  onApprove,
  busy,
}: {
  actions: ActionRecord[];
  activeConversation: boolean;
  onApprove: (actionId: string, approve: boolean) => void;
  busy: boolean;
}) {
  const [filter, setFilter] = useState<"all" | ActionStatus>("all");
  const filtered = useMemo(
    () => (filter === "all" ? actions : actions.filter((action) => action.status === filter)),
    [actions, filter],
  );

  return (
    <div className="panel-scroll">
      <section className="panel-section">
        <div className="section-title">
          <span>HISTÓRICO DE AÇÕES</span>
          <span className="section-badge">{actions.length}</span>
        </div>
        <div className="action-filters">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              className={`filter-chip ${filter === item.id ? "active" : ""}`}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      {filtered.length === 0 ? (
        <div className="panel-empty">
          {activeConversation
            ? "Nenhuma ação registrada para este filtro."
            : "Abra uma conversa para ver as ações executadas."}
        </div>
      ) : (
        <section className="panel-section action-list">
          {filtered.map((action) => {
            const success = action.status === "executed";
            const failed = action.status === "failed" || action.status === "blocked";
            const pending = action.status === "pending";
            return (
              <article
                key={action.id}
                className={`action-card ${success ? "action-ok" : ""} ${
                  failed ? "action-fail" : ""
                } ${pending ? "action-pending" : ""}`}
              >
                <div className="action-head">
                  <span className={`level-badge level-${action.permission_level}`}>
                    NÍVEL {action.permission_level}
                  </span>
                  <span className="action-tool">{action.tool_name}</span>
                  <span className={`action-status status-${action.status}`}>
                    {STATUS_LABEL[action.status] ?? action.status}
                  </span>
                </div>
                <div className="action-summary">{action.summary}</div>
                <div className="action-meta">
                  <span>{formatTime(action.created_at)}</span>
                  <span>·</span>
                  <span>{duration(action)}</span>
                </div>
                <details className="action-details">
                  <summary>Argumentos e resultado</summary>
                  <div className="action-detail-block">
                    <span className="detail-label">Argumentos</span>
                    <pre>{JSON.stringify(action.arguments, null, 2)}</pre>
                  </div>
                  {action.result ? (
                    <div className="action-detail-block">
                      <span className="detail-label">Resultado</span>
                      <pre>{JSON.stringify(action.result, null, 2).slice(0, 5000)}</pre>
                    </div>
                  ) : null}
                  {action.error ? (
                    <div className="action-detail-block">
                      <span className="detail-label">Erro</span>
                      <pre className="error-text">{action.error}</pre>
                    </div>
                  ) : null}
                </details>
                {pending ? (
                  <div className="confirmation-actions compact">
                    <button
                      className="approve"
                      onClick={() => onApprove(action.id, true)}
                      disabled={busy}
                    >
                      Aprovar
                    </button>
                    <button
                      className="deny"
                      onClick={() => onApprove(action.id, false)}
                      disabled={busy}
                    >
                      Recusar
                    </button>
                  </div>
                ) : null}
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}
