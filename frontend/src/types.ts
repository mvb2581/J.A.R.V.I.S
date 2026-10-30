export type ProviderId = "deepseek" | "openai" | "anthropic" | "ollama" | "custom";

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  archived: boolean;
  metadata: Record<string, unknown>;
  message_count: number;
  last_message: string;
}

export interface ToolCall {
  id: string;
  type: string;
  function: { name: string; arguments: string };
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  tool_calls?: ToolCall[] | null;
  tool_call_id?: string | null;
  name?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export type ActionStatus =
  | "pending"
  | "executing"
  | "executed"
  | "failed"
  | "denied"
  | "blocked";

export interface ActionRecord {
  id: string;
  conversation_id?: string | null;
  tool_call_id?: string | null;
  tool_name: string;
  arguments: Record<string, unknown>;
  permission_level: number;
  status: ActionStatus;
  summary: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface MemoryRecord {
  id: string;
  category: "preference" | "fact" | "project" | "contact" | "other";
  content: string;
  source: string;
  persistent: boolean;
  conversation_id?: string | null;
  created_at: string;
  updated_at: string;
  last_used_at?: string | null;
}

export type PlanStatus = "pending" | "in_progress" | "done" | "blocked";

export interface PlanStep {
  id: number;
  title: string;
  status: PlanStatus;
  note: string;
}

export interface RuntimeState {
  online: boolean;
  listening: boolean;
  thinking: boolean;
  executing: boolean;
  speaking: boolean;
  detail: string;
  error?: string | null;
  active_tool?: string | null;
  active_conversation_id?: string | null;
  state: "idle" | "listening" | "thinking" | "executing" | "speaking" | "error";
}

export interface GpuInfo {
  name: string;
  vendor?: string;
  utilization_percent?: number | null;
  memory_total_mb?: number;
  memory_used_mb?: number;
  temperature_c?: number;
}

export interface ResourceUsage {
  cpu_percent: number;
  cpu_cores_logical?: number;
  cpu_cores_physical?: number;
  ram_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  swap_percent?: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
  network_sent_mb?: number;
  network_received_mb?: number;
  gpus: GpuInfo[];
  battery?: { percent: number; plugged: boolean; seconds_left?: number | null } | null;
  processes?: number;
  uptime_seconds?: number;
}

export interface VoiceStatus {
  active: boolean;
  engine: "google" | "whisper";
  language: string;
  wake_word_enabled: boolean;
  wake_word: string;
  continuous_listening: boolean;
  microphone: string;
  input_device_index: number | null;
  busy: boolean;
  wake_mode_active: boolean;
  voice_confirm_actions: boolean;
}

export interface SystemStatus {
  runtime: RuntimeState;
  resources: ResourceUsage;
  database: { healthy: boolean; path: string };
  provider: { id: ProviderId; model: string; configured: boolean };
  voice: VoiceStatus;
  tools: number;
  version: string;
}

export interface Settings {
  provider: ProviderId;
  model: string;
  temperature: number;
  max_tokens: number;
  max_agent_steps: number;
  context_messages: number;
  max_tool_result_chars: number;
  confirm_level2: boolean;
  allow_level3: boolean;
  allowed_roots: string[];
  block_sensitive_files: boolean;
  terminal_enabled: boolean;
  terminal_timeout_seconds: number;
  max_terminal_output_chars: number;
  voice_language: string;
  stt_engine: "google" | "whisper";
  whisper_model: string;
  input_device_index: number | null;
  stt_timeout_seconds: number;
  stt_phrase_limit_seconds: number;
  wake_word_required: boolean;
  tts_engine: "sapi" | "edge";
  tts_voice: string;
  tts_rate: number;
  tts_volume: number;
  auto_speak_voice: boolean;
  auto_speak_text: boolean;
  wake_word_enabled: boolean;
  wake_word: string;
  continuous_listening: boolean;
  voice_command_timeout: number;
  voice_confirm_actions: boolean;
  auto_memory_search: boolean;
  temporary_memory_ttl_hours: number;
  system_prompt_extra: string;
}

export interface ProviderInfo {
  id: ProviderId;
  label: string;
  requires_key: boolean;
  configured: boolean;
  key_source: "env" | "store" | "none";
  key_configured_in_store: boolean;
  base_url: string;
  model_hints: string[];
  current: boolean;
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  permission_level: number;
  parameters: Record<string, unknown>;
  enabled: boolean;
}

export interface MicrophoneInfo {
  index: number;
  name: string;
  channels: number;
  sample_rate: number;
}

export interface ChatResponse {
  conversation_id: string;
  conversation: Conversation | null;
  user_message: Message | null;
  messages: Message[];
  assistant_message: Message | null;
  pending_actions: ActionRecord[];
  plan: PlanStep[];
  cancelled: boolean;
  steps: number;
  usage: Record<string, number>;
}

export interface WsEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp?: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
  plan: PlanStep[];
  pending_actions: ActionRecord[];
}
