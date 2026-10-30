import type {
  ActionRecord,
  ChatResponse,
  Conversation,
  ConversationDetail,
  MemoryRecord,
  MicrophoneInfo,
  PlanStep,
  ProviderInfo,
  Settings,
  SystemStatus,
  ToolInfo,
  VoiceStatus,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (error) {
    throw new ApiError(
      "Não foi possível conectar ao backend do JARVIS. Verifique se o servidor está em execução.",
      0,
      error,
    );
  }
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const payload = data as Record<string, unknown> | null;
    const detail = payload?.detail;
    let message = payload?.message as string | undefined;
    if (!message && typeof detail === "string") message = detail;
    if (!message && detail && typeof detail === "object") {
      const object = detail as Record<string, unknown>;
      message = (object.message as string) || (object.code as string);
    }
    if (!message && typeof data === "string") message = data;
    throw new ApiError(message || `Erro HTTP ${response.status}`, response.status, detail);
  }
  return data as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),
  status: () => request<SystemStatus>("/api/status"),
  tools: () => request<{ tools: ToolInfo[] }>("/api/tools"),

  getSettings: () => request<{ settings: Settings }>("/api/settings"),
  updateSettings: (values: Partial<Settings>) =>
    request<{ settings: Settings }>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ values }),
    }),
  resetSettings: () =>
    request<{ settings: Settings }>("/api/settings/reset", { method: "POST" }),

  providers: () => request<{ providers: ProviderInfo[] }>("/api/providers"),
  testProvider: (id: string) =>
    request<{ ok: boolean; message: string; models: string[] }>(`/api/providers/${id}/test`, {
      method: "POST",
    }),
  providerModels: (id: string) =>
    request<{ models: string[] }>(`/api/providers/${id}/models`),
  setProviderKey: (id: string, apiKey: string) =>
    request<{ ok: boolean }>(`/api/providers/${id}/key`, {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    }),
  deleteProviderKey: (id: string) =>
    request<{ ok: boolean }>(`/api/providers/${id}/key`, { method: "DELETE" }),

  conversations: () =>
    request<{ conversations: Conversation[] }>("/api/conversations"),
  createConversation: (title = "Nova conversa") =>
    request<{ conversation: Conversation }>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  conversation: (id: string) =>
    request<ConversationDetail>(`/api/conversations/${id}`),
  updateConversation: (id: string, values: { title?: string; archived?: boolean }) =>
    request<{ conversation: Conversation }>(`/api/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(values),
    }),
  deleteConversation: (id: string) =>
    request<{ ok: boolean }>(`/api/conversations/${id}`, { method: "DELETE" }),

  chat: (payload: {
    message: string;
    conversation_id?: string | null;
    source?: "text" | "voice";
    speak?: boolean | null;
  }) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cancel: (conversationId?: string | null) =>
    request<{ cancelled: boolean }>(
      `/api/cancel${conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ""}`,
      { method: "POST" },
    ),

  actions: (params?: { conversation_id?: string; status?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.conversation_id) search.set("conversation_id", params.conversation_id);
    if (params?.status) search.set("status", params.status);
    if (params?.limit) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<{ actions: ActionRecord[] }>(`/api/actions${query ? `?${query}` : ""}`);
  },
  pendingActions: (conversationId?: string | null) =>
    request<{ actions: ActionRecord[] }>(
      `/api/actions/pending${
        conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ""
      }`,
    ),
  approveAction: (id: string, approve: boolean, speak?: boolean | null) =>
    request<ChatResponse>(`/api/actions/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approve, speak }),
    }),

  memories: (params?: { category?: string; persistent?: boolean }) => {
    const search = new URLSearchParams();
    if (params?.category) search.set("category", params.category);
    if (params?.persistent !== undefined) search.set("persistent", String(params.persistent));
    const query = search.toString();
    return request<{ memories: MemoryRecord[] }>(`/api/memories${query ? `?${query}` : ""}`);
  },
  searchMemories: (q: string, conversationId?: string | null) => {
    const search = new URLSearchParams({ q });
    if (conversationId) search.set("conversation_id", conversationId);
    return request<{ memories: MemoryRecord[] }>(`/api/memories/search?${search.toString()}`);
  },
  createMemory: (payload: {
    content: string;
    category: MemoryRecord["category"];
    persistent: boolean;
    conversation_id?: string | null;
  }) =>
    request<{ memory: MemoryRecord }>("/api/memories", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateMemory: (
    id: string,
    payload: Partial<Pick<MemoryRecord, "content" | "category" | "persistent">>,
  ) =>
    request<{ memory: MemoryRecord }>(`/api/memories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteMemory: (id: string) =>
    request<{ ok: boolean }>(`/api/memories/${id}`, { method: "DELETE" }),

  voiceStatus: () => request<{ voice: VoiceStatus }>("/api/voice/status"),
  voiceStart: (continuous?: boolean) =>
    request<{ voice: VoiceStatus }>("/api/voice/start", {
      method: "POST",
      body: JSON.stringify({ continuous }),
    }),
  voiceStop: () => request<{ voice: VoiceStatus }>("/api/voice/stop", { method: "POST" }),
  voiceListen: () =>
    request<{ recognized: string; response: ChatResponse | null }>("/api/voice/listen", {
      method: "POST",
    }),
  microphones: () => request<{ microphones: MicrophoneInfo[] }>("/api/voice/microphones"),
  speak: (text: string) =>
    request<{ ok: boolean }>("/api/voice/speak", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  stopSpeaking: () => request<{ ok: boolean }>("/api/voice/stop-speaking", { method: "POST" }),

  plan: (conversationId: string) =>
    request<{ plan: PlanStep[] }>(`/api/conversations/${conversationId}/plan`),
  updatePlan: (conversationId: string, steps: PlanStep[]) =>
    request<{ plan: PlanStep[] }>(`/api/conversations/${conversationId}/plan`, {
      method: "PUT",
      body: JSON.stringify({
        steps: steps.map(({ title, status, note }) => ({ title, status, note })),
      }),
    }),
};
