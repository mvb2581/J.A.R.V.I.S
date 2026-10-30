import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type {
  MicrophoneInfo,
  ProviderInfo,
  Settings,
  Settings as SettingsType,
} from "../types";

type SaveSettings = (values: Partial<SettingsType>) => Promise<SettingsType | null>;

function Section({
  title,
  subtitle,
  children,
  defaultOpen = false,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details className="settings-section" open={defaultOpen}>
      <summary>
        <span>{title}</span>
        {subtitle ? <span className="settings-subtitle">{subtitle}</span> : null}
      </summary>
      <div className="settings-body">{children}</div>
    </details>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span className="toggle-text">
        <span>{label}</span>
        {hint ? <span className="toggle-hint">{hint}</span> : null}
      </span>
      <span className={`switch ${checked ? "on" : ""}`}>
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="switch-knob" />
      </span>
    </label>
  );
}

function NumberField({
  label,
  hint,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        type="number"
        value={Number.isFinite(value) ? value : min}
        min={min}
        max={max}
        step={step ?? 1}
        onChange={(event) => {
          const parsed = Number(event.target.value);
          if (Number.isFinite(parsed)) onChange(parsed);
        }}
      />
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

export function SettingsPanel({
  settings,
  providers,
  onSave,
  onReset,
  onSaveKey,
  onRemoveKey,
  onTestProvider,
  onFetchModels,
}: {
  settings: Settings | null;
  providers: ProviderInfo[];
  onSave: SaveSettings;
  onReset: () => Promise<void>;
  onSaveKey: (provider: string, key: string) => Promise<boolean>;
  onRemoveKey: (provider: string) => Promise<void>;
  onTestProvider: (provider: string) => Promise<{ ok: boolean; message: string } | null>;
  onFetchModels: (provider: string) => Promise<string[]>;
}) {
  const [draft, setDraft] = useState<Settings | null>(settings);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [keyWorking, setKeyWorking] = useState<string | null>(null);
  const [microphones, setMicrophones] = useState<MicrophoneInfo[]>([]);
  const [micError, setMicError] = useState<string | null>(null);
  const [newRoot, setNewRoot] = useState("");

  useEffect(() => {
    setDraft(settings);
    setDirty(false);
  }, [settings]);

  const currentProvider = useMemo(
    () => providers.find((provider) => provider.id === draft?.provider),
    [providers, draft?.provider],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .microphones()
      .then((result) => {
        if (!cancelled) {
          setMicrophones(result.microphones);
          setMicError(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMicrophones([]);
          setMicError(
            error instanceof Error ? error.message : "Não foi possível listar os microfones.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!draft) {
    return <div className="panel-empty">Carregando configurações…</div>;
  }

  const update = <K extends keyof SettingsType>(key: K, value: SettingsType[K]) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
    setDirty(true);
  };

  const save = async () => {
    if (!draft || saving) return;
    setSaving(true);
    try {
      const result = await onSave(draft);
      if (result) setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  const runTest = async () => {
    if (!draft || testing) return;
    setTesting(true);
    try {
      await onTestProvider(draft.provider);
    } finally {
      setTesting(false);
    }
  };

  const loadModels = async () => {
    if (!draft || modelsLoading) return;
    setModelsLoading(true);
    try {
      const result = await onFetchModels(draft.provider);
      setModels(result);
    } finally {
      setModelsLoading(false);
    }
  };

  const saveKey = async (providerId: string) => {
    const key = (keyInputs[providerId] ?? "").trim();
    if (!key) return;
    setKeyWorking(providerId);
    try {
      const ok = await onSaveKey(providerId, key);
      if (ok) setKeyInputs((current) => ({ ...current, [providerId]: "" }));
    } finally {
      setKeyWorking(null);
    }
  };

  const addRoot = () => {
    const value = newRoot.trim();
    if (!value) return;
    if (draft.allowed_roots.includes(value)) {
      setNewRoot("");
      return;
    }
    update("allowed_roots", [...draft.allowed_roots, value]);
    setNewRoot("");
  };

  return (
    <div className="panel-scroll settings-panel">
      <div className="settings-toolbar">
        <span className={`settings-dirty ${dirty ? "visible" : ""}`}>
          {dirty ? "Alterações não salvas" : "Configurações sincronizadas"}
        </span>
        <div className="settings-toolbar-actions">
          <button
            className="ghost-button small"
            onClick={() => {
              if (window.confirm("Restaurar todas as configurações padrão?")) {
                void onReset();
              }
            }}
            disabled={saving}
          >
            Restaurar padrões
          </button>
          <button className="primary-button small" onClick={() => void save()} disabled={saving || !dirty}>
            {saving ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </div>

      <Section title="MODELO E PROVEDOR" defaultOpen>
        <label className="field">
          <span className="field-label">Provedor</span>
          <select
            value={draft.provider}
            onChange={(event) => {
              update("provider", event.target.value as SettingsType["provider"]);
              setModels([]);
            }}
          >
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.label}
                {provider.configured ? " ✓" : provider.requires_key ? " (sem chave)" : ""}
              </option>
            ))}
          </select>
          {currentProvider ? (
            <span className="field-hint">
              Chave:{" "}
              {currentProvider.key_source === "env"
                ? "variável de ambiente"
                : currentProvider.key_source === "store"
                  ? "cofre DPAPI local"
                  : currentProvider.requires_key
                    ? "não configurada"
                    : "não necessária"}
              {currentProvider.base_url ? ` · ${currentProvider.base_url}` : ""}
            </span>
          ) : null}
        </label>

        <label className="field">
          <span className="field-label">Modelo</span>
          <input
            value={draft.model}
            onChange={(event) => update("model", event.target.value)}
            list="jarvis-model-list"
            placeholder={currentProvider?.model_hints[0] ?? "nome-do-modelo"}
          />
          <datalist id="jarvis-model-list">
            {[...models, ...(currentProvider?.model_hints ?? [])].map((model) => (
              <option key={model} value={model} />
            ))}
          </datalist>
          <span className="field-hint">
            {currentProvider?.model_hints.length
              ? `Sugestões: ${currentProvider.model_hints.join(", ")}`
              : "Informe o identificador exato do modelo."}
          </span>
        </label>

        <div className="settings-inline-actions">
          <button className="ghost-button small" onClick={() => void runTest()} disabled={testing}>
            {testing ? "Testando…" : "Testar conexão"}
          </button>
          <button
            className="ghost-button small"
            onClick={() => void loadModels()}
            disabled={modelsLoading}
          >
            {modelsLoading ? "Consultando…" : "Listar modelos"}
          </button>
          {models.length > 0 ? (
            <span className="field-hint">{models.length} modelos disponíveis</span>
          ) : null}
        </div>

        <div className="settings-grid">
          <NumberField
            label="Temperatura"
            value={draft.temperature}
            min={0}
            max={2}
            step={0.1}
            onChange={(value) => update("temperature", value)}
            hint="0 = objetivo, 2 = criativo"
          />
          <NumberField
            label="Máx. tokens"
            value={draft.max_tokens}
            min={256}
            max={32768}
            step={256}
            onChange={(value) => update("max_tokens", value)}
          />
          <NumberField
            label="Passos do agente"
            value={draft.max_agent_steps}
            min={1}
            max={30}
            onChange={(value) => update("max_agent_steps", value)}
            hint="Limite de chamadas de ferramenta por resposta"
          />
          <NumberField
            label="Mensagens de contexto"
            value={draft.context_messages}
            min={4}
            max={200}
            onChange={(value) => update("context_messages", value)}
          />
          <NumberField
            label="Máx. caracteres por resultado"
            value={draft.max_tool_result_chars}
            min={2000}
            max={60000}
            step={1000}
            onChange={(value) => update("max_tool_result_chars", value)}
          />
        </div>
      </Section>

      <Section title="CHAVES DE API" subtitle="Cofre DPAPI local">
        <p className="settings-note">
          As chaves são criptografadas com DPAPI do Windows e gravadas em{" "}
          <code>data/secrets.json</code>. Variáveis de ambiente têm precedência e nunca são
          sobrescritas.
        </p>
        {providers.map((provider) => (
          <div className="key-row" key={provider.id}>
            <div className="key-provider">
              <strong>{provider.label}</strong>
              <span className={`key-source source-${provider.key_source}`}>
                {provider.key_source === "env"
                  ? "via .env"
                  : provider.key_source === "store"
                    ? "no cofre"
                    : provider.requires_key
                      ? "ausente"
                      : "sem chave"}
              </span>
            </div>
            <div className="key-controls">
              <input
                type="password"
                value={keyInputs[provider.id] ?? ""}
                onChange={(event) =>
                  setKeyInputs((current) => ({ ...current, [provider.id]: event.target.value }))
                }
                placeholder={provider.requires_key ? "Cole a chave de API" : "Não requer chave"}
                disabled={!provider.requires_key || provider.key_source === "env"}
                autoComplete="off"
                spellCheck={false}
              />
              <button
                className="ghost-button small"
                onClick={() => void saveKey(provider.id)}
                disabled={
                  !provider.requires_key ||
                  provider.key_source === "env" ||
                  !(keyInputs[provider.id] ?? "").trim() ||
                  keyWorking === provider.id
                }
              >
                {keyWorking === provider.id ? "Salvando…" : "Salvar"}
              </button>
              {provider.key_configured_in_store ? (
                <button
                  className="danger-button small"
                  onClick={() => void onRemoveKey(provider.id)}
                  disabled={keyWorking === provider.id}
                >
                  Remover
                </button>
              ) : null}
            </div>
          </div>
        ))}
      </Section>

      <Section title="PERMISSÕES E SEGURANÇA">
        <Toggle
          label="Confirmar ações de nível 2"
          hint="Alterações de arquivos, processos e automação pedem aprovação."
          checked={draft.confirm_level2}
          onChange={(value) => update("confirm_level2", value)}
        />
        <Toggle
          label="Permitir ações de nível 3"
          hint="Ações críticas (terminal, encerrar processos, mouse/teclado) sempre exigem confirmação explícita."
          checked={draft.allow_level3}
          onChange={(value) => update("allow_level3", value)}
        />
        <Toggle
          label="Bloquear arquivos sensíveis"
          hint="Protege .env, chaves SSH, cofres de senha e o banco do JARVIS."
          checked={draft.block_sensitive_files}
          onChange={(value) => update("block_sensitive_files", value)}
        />

        <div className="field">
          <span className="field-label">Diretórios autorizados</span>
          <div className="roots-list">
            {draft.allowed_roots.map((root) => (
              <div className="root-chip" key={root}>
                <span title={root}>{root}</span>
                <button
                  className="root-remove"
                  onClick={() =>
                    update(
                      "allowed_roots",
                      draft.allowed_roots.filter((item) => item !== root),
                    )
                  }
                  title="Remover diretório"
                  disabled={draft.allowed_roots.length <= 1}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <div className="root-add">
            <input
              value={newRoot}
              onChange={(event) => setNewRoot(event.target.value)}
              placeholder="C:\Users\Nome\Pasta"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addRoot();
                }
              }}
            />
            <button className="ghost-button small" onClick={addRoot} disabled={!newRoot.trim()}>
              Adicionar
            </button>
          </div>
          <span className="field-hint">
            O JARVIS só acessa arquivos dentro destes diretórios. Não é possível gravar na raiz de
            um diretório autorizado.
          </span>
        </div>
      </Section>

      <Section title="TERMINAL">
        <Toggle
          label="Permitir comandos de terminal"
          hint="Comandos destrutivos e a desativação de proteções do Windows continuam bloqueados."
          checked={draft.terminal_enabled}
          onChange={(value) => update("terminal_enabled", value)}
        />
        <div className="settings-grid">
          <NumberField
            label="Timeout (s)"
            value={draft.terminal_timeout_seconds}
            min={5}
            max={600}
            onChange={(value) => update("terminal_timeout_seconds", value)}
          />
          <NumberField
            label="Máx. saída (caracteres)"
            value={draft.max_terminal_output_chars}
            min={1000}
            max={100000}
            step={1000}
            onChange={(value) => update("max_terminal_output_chars", value)}
          />
        </div>
      </Section>

      <Section title="VOZ E ESCUTA">
        <div className="settings-grid">
          <label className="field">
            <span className="field-label">Idioma</span>
            <input
              value={draft.voice_language}
              onChange={(event) => update("voice_language", event.target.value)}
              placeholder="pt-BR"
            />
          </label>
          <label className="field">
            <span className="field-label">Motor STT</span>
            <select
              value={draft.stt_engine}
              onChange={(event) =>
                update("stt_engine", event.target.value as SettingsType["stt_engine"])
              }
            >
              <option value="google">Google (online)</option>
              <option value="whisper">Whisper local</option>
            </select>
          </label>
          {draft.stt_engine === "whisper" ? (
            <label className="field">
              <span className="field-label">Modelo Whisper</span>
              <select
                value={draft.whisper_model}
                onChange={(event) => update("whisper_model", event.target.value)}
              >
                {["tiny", "base", "small", "medium", "large-v3"].map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="field">
            <span className="field-label">Microfone</span>
            <select
              value={draft.input_device_index === null ? "" : String(draft.input_device_index)}
              onChange={(event) =>
                update(
                  "input_device_index",
                  event.target.value === "" ? null : Number(event.target.value),
                )
              }
            >
              <option value="">Padrão do sistema</option>
              {microphones.map((microphone) => (
                <option key={microphone.index} value={microphone.index}>
                  {microphone.name}
                </option>
              ))}
            </select>
            {micError ? <span className="field-hint error-text">{micError}</span> : null}
          </label>
          <NumberField
            label="Timeout de escuta (s)"
            value={draft.stt_timeout_seconds}
            min={2}
            max={60}
            step={1}
            onChange={(value) => update("stt_timeout_seconds", value)}
          />
          <NumberField
            label="Duração máx. da frase (s)"
            value={draft.stt_phrase_limit_seconds}
            min={3}
            max={60}
            step={1}
            onChange={(value) => update("stt_phrase_limit_seconds", value)}
          />
        </div>

        <Toggle
          label="Escuta por palavra-chave"
          hint="O microfone só é aberto quando você ativa a escuta."
          checked={draft.wake_word_enabled}
          onChange={(value) => update("wake_word_enabled", value)}
        />
        <div className="settings-grid">
          <label className="field">
            <span className="field-label">Palavra-chave</span>
            <input
              value={draft.wake_word}
              onChange={(event) => update("wake_word", event.target.value)}
              placeholder="jarvis"
            />
          </label>
          <NumberField
            label="Espera pelo comando (s)"
            value={draft.voice_command_timeout}
            min={2}
            max={30}
            onChange={(value) => update("voice_command_timeout", value)}
          />
        </div>
        <Toggle
          label="Exigir a palavra-chave"
          hint="Se desativado, qualquer fala capturada na escuta contínua é tratada como comando."
          checked={draft.wake_word_required}
          onChange={(value) => update("wake_word_required", value)}
        />
        <Toggle
          label="Escuta contínua"
          hint="Retoma automaticamente o microfone após cada resposta."
          checked={draft.continuous_listening}
          onChange={(value) => update("continuous_listening", value)}
        />
        <Toggle
          label="Confirmar ações por voz"
          hint="Aceita “sim”/“não” falados para aprovar ou recusar ações pendentes."
          checked={draft.voice_confirm_actions}
          onChange={(value) => update("voice_confirm_actions", value)}
        />
      </Section>

      <Section title="SÍNTESE DE VOZ">
        <div className="settings-grid">
          <label className="field">
            <span className="field-label">Motor TTS</span>
            <select
              value={draft.tts_engine}
              onChange={(event) =>
                update("tts_engine", event.target.value as SettingsType["tts_engine"])
              }
            >
              <option value="sapi">SAPI (Windows)</option>
              <option value="edge">Edge TTS (online)</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Voz</span>
            <input
              value={draft.tts_voice}
              onChange={(event) => update("tts_voice", event.target.value)}
              placeholder="padrão do sistema"
            />
          </label>
          <NumberField
            label="Velocidade"
            value={draft.tts_rate}
            min={80}
            max={400}
            onChange={(value) => update("tts_rate", value)}
          />
          <label className="field">
            <span className="field-label">Volume</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={draft.tts_volume}
              onChange={(event) => update("tts_volume", Number(event.target.value))}
            />
            <span className="field-hint">{Math.round(draft.tts_volume * 100)}%</span>
          </label>
        </div>
        <Toggle
          label="Falar respostas de voz"
          hint="Respostas a comandos falados são sintetizadas automaticamente."
          checked={draft.auto_speak_voice}
          onChange={(value) => update("auto_speak_voice", value)}
        />
        <Toggle
          label="Falar respostas de texto"
          hint="Também sintetiza respostas enviadas pelo chat."
          checked={draft.auto_speak_text}
          onChange={(value) => update("auto_speak_text", value)}
        />
      </Section>

      <Section title="MEMÓRIA E COMPORTAMENTO">
        <Toggle
          label="Busca automática de memórias"
          hint="Recupera memórias relevantes antes de cada resposta."
          checked={draft.auto_memory_search}
          onChange={(value) => update("auto_memory_search", value)}
        />
        <NumberField
          label="Validade de memórias temporárias (horas)"
          value={draft.temporary_memory_ttl_hours}
          min={1}
          max={720}
          onChange={(value) => update("temporary_memory_ttl_hours", value)}
        />
        <label className="field">
          <span className="field-label">Instruções adicionais para o JARVIS</span>
          <textarea
            value={draft.system_prompt_extra}
            onChange={(event) => update("system_prompt_extra", event.target.value)}
            rows={4}
            maxLength={4000}
            placeholder="Ex.: chame-me de senhor; prefira respostas curtas; projetos ficam em C:\Projetos."
          />
          <span className="field-hint">{draft.system_prompt_extra.length}/4000</span>
        </label>
      </Section>

      <div className="settings-footer">
        <button className="primary-button" onClick={() => void save()} disabled={saving || !dirty}>
          {saving ? "Salvando…" : "Salvar configurações"}
        </button>
      </div>
    </div>
  );
}
