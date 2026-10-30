import type { RuntimeState, Settings, VoiceStatus } from "../types";

function ReactorMark() {
  return (
    <svg className="reactor-mark" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="28" className="reactor-outer" />
      <circle cx="32" cy="32" r="20" className="reactor-mid" />
      <circle cx="32" cy="32" r="9" className="reactor-core" />
      <path d="M32 4v10M32 50v10M4 32h10M50 32h10" className="reactor-line" />
      <path d="M12 12l7 7M45 45l7 7M52 12l-7 7M19 45l-7 7" className="reactor-line" />
    </svg>
  );
}

export function TopBar({
  runtime,
  voice,
  settings,
  connected,
  voiceBusy,
  onToggleWake,
  onListen,
  onStop,
  onStopSpeaking,
  onOpenSettings,
}: {
  runtime: RuntimeState;
  voice: VoiceStatus | null;
  settings: Settings | null;
  connected: boolean;
  voiceBusy: boolean;
  onToggleWake: () => void;
  onListen: () => void;
  onStop: () => void;
  onStopSpeaking: () => void;
  onOpenSettings: () => void;
}) {
  const wakeActive = Boolean(voice?.wake_mode_active);
  const listening = runtime.listening;
  return (
    <header className="topbar">
      <div className="brand">
        <ReactorMark />
        <div>
          <div className="brand-title">
            J.A.R.V.I.S<span className="brand-cursor">_</span>
          </div>
          <div className="brand-sub">PERSONAL AI SYSTEM · WINDOWS</div>
        </div>
      </div>

      <div className="topbar-status">
        <span className={`connection ${connected ? "online" : "offline"}`}>
          <span className={`status-dot ${connected ? "ok" : "fail"}`} />
          {connected ? "ONLINE" : "OFFLINE"}
        </span>
        <span className="divider" />
        <span className="model-chip">
          {settings ? `${settings.provider.toUpperCase()} / ${settings.model}` : "SEM MODELO"}
        </span>
        <span className="divider" />
        <span className={`state-chip state-${runtime.state}`}>{runtime.detail || runtime.state}</span>
      </div>

      <div className="topbar-actions">
        <button
          className={`action-button wake ${wakeActive ? "active" : ""}`}
          onClick={onToggleWake}
          disabled={voiceBusy}
          title={wakeActive ? "Desativar escuta por palavra-chave" : "Ativar escuta por palavra-chave"}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 3v10a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v4a3 3 0 0 0 3 3Z" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
          </svg>
          <span>{wakeActive ? "ESCUTA ATIVA" : "PALAVRA-CHAVE"}</span>
        </button>
        <button
          className={`action-button listen ${listening ? "active" : ""}`}
          onClick={onListen}
          disabled={voiceBusy}
          title="Falar um comando agora (push-to-talk)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 12a8 8 0 0 1 16 0M6 12v4a2 2 0 0 0 2 2h1M18 12v4a2 2 0 0 1-2 2h-1" />
            <circle cx="12" cy="12" r="2.4" />
          </svg>
          <span>FALAR</span>
        </button>
        <button className="action-button stop" onClick={onStop} title="Interromper execução e fala">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
          <span>PARAR</span>
        </button>
        {runtime.speaking ? (
          <button className="action-button" onClick={onStopSpeaking} title="Silenciar resposta">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 9v6h4l5 4V5L8 9H4ZM17 9l4 6M21 9l-4 6" />
            </svg>
          </button>
        ) : null}
        <button className="icon-button settings-button" onClick={onOpenSettings} title="Configurações">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.1.36.3.7.6 1 .3.3.7.4 1.1.4H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51.6Z" />
          </svg>
        </button>
      </div>
    </header>
  );
}
