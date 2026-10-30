import type { RuntimeState } from "../types";

const LABELS: Record<RuntimeState["state"], string> = {
  idle: "SISTEMA ONLINE",
  listening: "OUVINDO",
  thinking: "PROCESSANDO",
  executing: "EXECUTANDO",
  speaking: "RESPONDENDO",
  error: "ATENÇÃO",
};

export function Orb({
  state,
  detail,
  compact = false,
}: {
  state: RuntimeState["state"];
  detail?: string;
  compact?: boolean;
}) {
  return (
    <div className={`orb-wrap ${compact ? "orb-compact" : ""} orb-${state}`}>
      <div className="orb">
        <div className="orb-ring ring-1" />
        <div className="orb-ring ring-2" />
        <div className="orb-ring ring-3" />
        <div className="orb-ticks" />
        <div className="orb-core">
          <div className="orb-core-inner" />
        </div>
        <div className="orb-scan" />
      </div>
      <div className="orb-caption">
        <span className="orb-label">{LABELS[state]}</span>
        {detail ? <span className="orb-detail">{detail}</span> : null}
      </div>
    </div>
  );
}
