import { useMemo } from "react";
import type { PlanStatus, PlanStep } from "../types";

const STATUS_LABEL: Record<PlanStatus, string> = {
  pending: "Pendente",
  in_progress: "Em execução",
  done: "Concluída",
  blocked: "Bloqueada",
};

const STATUS_ICON: Record<PlanStatus, string> = {
  pending: "○",
  in_progress: "◐",
  done: "●",
  blocked: "✕",
};

export function PlanPanel({
  plan,
  activeConversation,
}: {
  plan: PlanStep[];
  activeConversation: boolean;
}) {
  const progress = useMemo(() => {
    if (plan.length === 0) return { done: 0, total: 0, percent: 0 };
    const done = plan.filter((step) => step.status === "done").length;
    return { done, total: plan.length, percent: Math.round((done / plan.length) * 100) };
  }, [plan]);

  if (!activeConversation) {
    return (
      <div className="panel-empty">
        Abra ou crie uma conversa para ver o plano de execução do JARVIS.
      </div>
    );
  }

  if (plan.length === 0) {
    return (
      <div className="panel-empty">
        Nenhum plano ativo nesta conversa.
        <br />
        Peça uma tarefa complexa, como “organize meus downloads”, e o JARVIS criará as etapas.
      </div>
    );
  }

  return (
    <div className="panel-scroll">
      <section className="panel-section">
        <div className="section-title">
          <span>PROGRESSO DA TAREFA</span>
          <span className="section-badge">
            {progress.done}/{progress.total}
          </span>
        </div>
        <div className="plan-progress">
          <div className="plan-progress-track">
            <div className="plan-progress-fill" style={{ width: `${progress.percent}%` }} />
          </div>
          <span className="plan-progress-label">{progress.percent}% concluído</span>
        </div>
      </section>

      <section className="panel-section">
        <ol className="plan-list">
          {plan.map((step) => (
            <li key={step.id} className={`plan-step plan-${step.status}`}>
              <div className="plan-marker" aria-hidden="true">
                {STATUS_ICON[step.status]}
              </div>
              <div className="plan-body">
                <div className="plan-step-title">{step.title}</div>
                {step.note ? <div className="plan-step-note">{step.note}</div> : null}
                <div className={`plan-status plan-status-${step.status}`}>
                  {STATUS_LABEL[step.status]}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <div className="panel-hint">
        O plano é atualizado automaticamente pelo JARVIS conforme as etapas avançam.
      </div>
    </div>
  );
}
