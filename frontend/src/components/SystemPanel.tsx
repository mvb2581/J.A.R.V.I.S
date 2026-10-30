import type { RuntimeState, SystemStatus, VoiceStatus } from "../types";

function Bar({
  label,
  value,
  detail,
  tone = "blue",
}: {
  label: string;
  value: number;
  detail: string;
  tone?: "blue" | "cyan" | "amber" | "violet";
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="metric">
      <div className="metric-head">
        <span>{label}</span>
        <span className="metric-value">{Math.round(clamped)}%</span>
      </div>
      <div className="metric-track">
        <div className={`metric-fill tone-${tone}`} style={{ width: `${clamped}%` }} />
      </div>
      <div className="metric-detail">{detail}</div>
    </div>
  );
}

function uptime(seconds?: number): string {
  if (!seconds || seconds < 0) return "—";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}min`;
  return `${minutes}min`;
}

export function SystemPanel({
  system,
  runtime,
  voice,
}: {
  system: SystemStatus | null;
  runtime: RuntimeState;
  voice: VoiceStatus | null;
}) {
  if (!system) {
    return <div className="panel-empty">Coletando telemetria do sistema…</div>;
  }
  const resources = system.resources;
  return (
    <div className="panel-scroll">
      <section className="panel-section">
        <div className="section-title">
          <span>TELEMETRIA</span>
          <span className={`status-dot ${runtime.online ? "ok" : "fail"}`} />
        </div>
        <div className="metrics">
          <Bar
            label="CPU"
            value={resources.cpu_percent}
            detail={`${resources.cpu_cores_physical ?? "?"} núcleos físicos · ${
              resources.cpu_cores_logical ?? "?"
            } lógicos`}
          />
          <Bar
            label="MEMÓRIA RAM"
            value={resources.ram_percent}
            detail={`${resources.ram_used_gb.toFixed(1)} GB de ${resources.ram_total_gb.toFixed(1)} GB`}
            tone="cyan"
          />
          <Bar
            label="DISCO C:"
            value={resources.disk_percent}
            detail={`${resources.disk_used_gb.toFixed(0)} GB de ${resources.disk_total_gb.toFixed(0)} GB`}
            tone="violet"
          />
          {typeof resources.swap_percent === "number" ? (
            <Bar
              label="MEMÓRIA VIRTUAL"
              value={resources.swap_percent}
              detail="Arquivo de paginação"
              tone="amber"
            />
          ) : null}
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">
          <span>GPU</span>
        </div>
        {resources.gpus.length === 0 ? (
          <div className="panel-empty small">Nenhuma GPU detectada.</div>
        ) : (
          resources.gpus.map((gpu) => (
            <div className="gpu-card" key={gpu.name}>
              <div className="gpu-name">{gpu.name}</div>
              {typeof gpu.utilization_percent === "number" ? (
                <>
                  <Bar
                    label="UTILIZAÇÃO"
                    value={gpu.utilization_percent}
                    detail={
                      gpu.memory_total_mb
                        ? `${Math.round(gpu.memory_used_mb ?? 0)} MB / ${Math.round(
                            gpu.memory_total_mb,
                          )} MB VRAM${gpu.temperature_c ? ` · ${gpu.temperature_c}°C` : ""}`
                        : "Uso atual"
                    }
                    tone="cyan"
                  />
                </>
              ) : (
                <div className="metric-detail">Telemetria detalhada indisponível (driver NVIDIA ausente).</div>
              )}
            </div>
          ))
        )}
      </section>

      <section className="panel-section grid-2">
        <div className="stat-card">
          <span className="stat-label">PROCESSOS</span>
          <span className="stat-value">{resources.processes ?? "—"}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">TEMPO LIGADO</span>
          <span className="stat-value">{uptime(resources.uptime_seconds)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">REDE ENVIADA</span>
          <span className="stat-value">{resources.network_sent_mb?.toFixed(0) ?? "—"} MB</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">REDE RECEBIDA</span>
          <span className="stat-value">{resources.network_received_mb?.toFixed(0) ?? "—"} MB</span>
        </div>
        {resources.battery ? (
          <div className="stat-card wide">
            <span className="stat-label">BATERIA</span>
            <span className="stat-value">
              {Math.round(resources.battery.percent)}% ·{" "}
              {resources.battery.plugged ? "na tomada" : "descarregando"}
            </span>
          </div>
        ) : null}
      </section>

      <section className="panel-section">
        <div className="section-title">
          <span>NÚCLEO</span>
        </div>
        <div className="kv-list">
          <div>
            <span>Provedor</span>
            <strong>{system.provider.id}</strong>
          </div>
          <div>
            <span>Modelo</span>
            <strong>{system.provider.model}</strong>
          </div>
          <div>
            <span>Configurado</span>
            <strong>{system.provider.configured ? "sim" : "não"}</strong>
          </div>
          <div>
            <span>Ferramentas</span>
            <strong>{system.tools}</strong>
          </div>
          <div>
            <span>Banco SQLite</span>
            <strong>{system.database.healthy ? "saudável" : "falha"}</strong>
          </div>
          <div>
            <span>Microfone</span>
            <strong>{voice?.microphone || "padrão do sistema"}</strong>
          </div>
          <div>
            <span>STT / TTS</span>
            <strong>
              {voice?.engine ?? "—"} / {system.voice.engine === "google" ? "google" : "whisper"} ·{" "}
              {voice?.language ?? "pt-BR"}
            </strong>
          </div>
          <div>
            <span>Versão</span>
            <strong>v{system.version}</strong>
          </div>
        </div>
      </section>
    </div>
  );
}
