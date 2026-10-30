import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";
import type {
  ActionRecord,
  ChatResponse,
  Conversation,
  MemoryRecord,
  Message,
  PlanStep,
  ProviderInfo,
  RuntimeState,
  Settings,
  SystemStatus,
  ToolInfo,
  VoiceStatus,
  WsEvent,
} from "./types";

const initialRuntime: RuntimeState = {
  online: false,
  listening: false,
  thinking: false,
  executing: false,
  speaking: false,
  detail: "Conectando…",
  state: "idle",
};

export type ToastKind = "info" | "success" | "error";

export interface Toast {
  message: string;
  kind: ToastKind;
}

function mergeMessages(current: Message[], incoming: Message[]): Message[] {
  const map = new Map(current.map((message) => [message.id, message]));
  for (const message of incoming) map.set(message.id, message);
  return [...map.values()].sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export function useJarvis() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [runtime, setRuntime] = useState<RuntimeState>(initialRuntime);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [plan, setPlan] = useState<PlanStep[]>([]);
  const [pendingActions, setPendingActions] = useState<ActionRecord[]>([]);
  const [actions, setActions] = useState<ActionRecord[]>([]);
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [voice, setVoice] = useState<VoiceStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  const activeIdRef = useRef<string | null>(null);
  const busyRef = useRef(false);
  const manualListenRef = useRef(false);
  const toastTimer = useRef<number | undefined>(undefined);

  const notify = useCallback((message: string, kind: ToastKind = "info") => {
    setToast({ message, kind });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), kind === "error" ? 8000 : 4500);
  }, []);

  const dismissToast = useCallback(() => {
    window.clearTimeout(toastTimer.current);
    setToast(null);
  }, []);

  const handleError = useCallback(
    (cause: unknown, fallback = "Ocorreu um erro inesperado.") => {
      const message =
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error
            ? cause.message
            : fallback;
      setError(message);
      notify(message, "error");
    },
    [notify],
  );

  const refreshConversations = useCallback(async () => {
    try {
      const result = await api.conversations();
      setConversations(result.conversations);
    } catch (cause) {
      handleError(cause, "Não foi possível carregar as conversas.");
    }
  }, [handleError]);

  const refreshProviders = useCallback(async () => {
    try {
      const result = await api.providers();
      setProviders(result.providers);
    } catch {
      /* silencioso: o painel mostra o estado anterior */
    }
  }, []);

  const refreshActions = useCallback(async () => {
    try {
      const result = await api.actions({ limit: 120 });
      setActions(result.actions);
    } catch {
      /* silencioso */
    }
  }, []);

  const loadMemories = useCallback(async () => {
    try {
      const result = await api.memories();
      setMemories(result.memories);
    } catch (cause) {
      handleError(cause, "Não foi possível carregar a memória.");
    }
  }, [handleError]);

  const refreshStatus = useCallback(async () => {
    try {
      const result = await api.status();
      setSystem(result);
      setRuntime(result.runtime);
      setVoice(result.voice);
    } catch {
      setRuntime((current) => ({ ...current, online: false, state: "error", detail: "Backend indisponível" }));
    }
  }, []);

  const changeActive = useCallback((id: string | null) => {
    activeIdRef.current = id;
    setActiveId(id);
  }, []);

  const selectConversation = useCallback(
    async (id: string | null) => {
      changeActive(id);
      if (!id) {
        setMessages([]);
        setPlan([]);
        setPendingActions([]);
        return;
      }
      try {
        const detail = await api.conversation(id);
        setMessages(detail.messages);
        setPlan(detail.plan);
        setPendingActions(detail.pending_actions);
        setConversations((current) =>
          current.map((conversation) =>
            conversation.id === id ? detail.conversation : conversation,
          ),
        );
        const result = await api.actions({ conversation_id: id, limit: 120 });
        setActions(result.actions);
      } catch (cause) {
        handleError(cause, "Não foi possível abrir a conversa.");
      }
    },
    [changeActive, handleError],
  );

  const applyChatResponse = useCallback(
    (response: ChatResponse) => {
      if (activeIdRef.current !== response.conversation_id) {
        changeActive(response.conversation_id);
        setMessages([]);
      }
      const incoming = [
        ...(response.user_message ? [response.user_message] : []),
        ...response.messages,
      ];
      setMessages((current) => mergeMessages(current, incoming));
      setPlan(response.plan);
      setPendingActions(response.pending_actions);
      setConversations((current) => {
        if (!response.conversation) return current;
        const exists = current.some((conversation) => conversation.id === response.conversation?.id);
        if (!exists) return [response.conversation, ...current];
        return current.map((conversation) =>
          conversation.id === response.conversation?.id ? response.conversation! : conversation,
        );
      });
      void refreshActions();
    },
    [changeActive, refreshActions],
  );

  const sendMessage = useCallback(
    async (text: string, source: "text" | "voice" = "text") => {
      const trimmed = text.trim();
      if (!trimmed || busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      setError(null);
      try {
        const response = await api.chat({
          message: trimmed,
          conversation_id: activeIdRef.current,
          source,
        });
        applyChatResponse(response);
        if (response.pending_actions.length > 0) {
          notify("Ação aguardando sua confirmação.", "info");
        }
        void refreshConversations();
      } catch (cause) {
        handleError(cause, "Falha ao enviar a mensagem.");
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [applyChatResponse, handleError, notify, refreshConversations],
  );

  const cancel = useCallback(async () => {
    try {
      await api.cancel(activeIdRef.current);
      notify("Execução interrompida.", "info");
      setRuntime((current) => ({ ...current, state: "idle", detail: "Interrompido" }));
    } catch (cause) {
      handleError(cause, "Não foi possível interromper.");
    }
  }, [handleError, notify]);

  const approveAction = useCallback(
    async (actionId: string, approve: boolean) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      try {
        const response = await api.approveAction(actionId, approve);
        applyChatResponse(response);
        setPendingActions((current) => current.filter((action) => action.id !== actionId));
        notify(approve ? "Ação aprovada e executada." : "Ação recusada.", approve ? "success" : "info");
        void refreshConversations();
      } catch (cause) {
        handleError(cause, "Falha ao processar a confirmação.");
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [applyChatResponse, handleError, notify, refreshConversations],
  );

  const newConversation = useCallback(async () => {
    try {
      const result = await api.createConversation();
      setConversations((current) => [result.conversation, ...current]);
      changeActive(result.conversation.id);
      setMessages([]);
      setPlan([]);
      setPendingActions([]);
    } catch (cause) {
      handleError(cause, "Não foi possível criar a conversa.");
    }
  }, [changeActive, handleError]);

  const deleteConversation = useCallback(
    async (id: string) => {
      try {
        await api.deleteConversation(id);
        setConversations((current) => current.filter((conversation) => conversation.id !== id));
        if (activeIdRef.current === id) {
          changeActive(null);
          setMessages([]);
          setPlan([]);
          setPendingActions([]);
        }
      } catch (cause) {
        handleError(cause, "Não foi possível excluir a conversa.");
      }
    },
    [changeActive, handleError],
  );

  const startVoice = useCallback(
    async (continuous?: boolean) => {
      setVoiceBusy(true);
      try {
        const result = await api.voiceStart(continuous);
        setVoice(result.voice);
        notify(
          result.voice.continuous_listening
            ? `Escuta contínua ativa. Diga “${result.voice.wake_word}”.`
            : `Escutando pela palavra-chave “${result.voice.wake_word}”.`,
          "success",
        );
      } catch (cause) {
        handleError(cause, "Não foi possível ativar o microfone.");
      } finally {
        setVoiceBusy(false);
      }
    },
    [handleError, notify],
  );

  const stopVoice = useCallback(async () => {
    setVoiceBusy(true);
    try {
      const result = await api.voiceStop();
      setVoice(result.voice);
      notify("Microfone desativado.", "info");
    } catch (cause) {
      handleError(cause, "Não foi possível desativar o microfone.");
    } finally {
      setVoiceBusy(false);
    }
  }, [handleError, notify]);

  const listenOnce = useCallback(async () => {
    if (voiceBusy) return;
    setVoiceBusy(true);
    manualListenRef.current = true;
    try {
      const result = await api.voiceListen();
      if (result.response) applyChatResponse(result.response);
      notify(`Ouvi: “${result.recognized}”`, "info");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        notify(cause.message, "info");
      } else {
        handleError(cause, "Falha no reconhecimento de voz.");
      }
    } finally {
      manualListenRef.current = false;
      setVoiceBusy(false);
    }
  }, [applyChatResponse, handleError, notify, voiceBusy]);

  const stopSpeaking = useCallback(async () => {
    try {
      await api.stopSpeaking();
    } catch (cause) {
      handleError(cause, "Não foi possível interromper a fala.");
    }
  }, [handleError]);

  const saveSettings = useCallback(
    async (values: Partial<Settings>) => {
      try {
        const result = await api.updateSettings(values);
        setSettings(result.settings);
        notify("Configurações salvas.", "success");
        void refreshStatus();
        void refreshProviders();
        return result.settings;
      } catch (cause) {
        handleError(cause, "Não foi possível salvar as configurações.");
        return null;
      }
    },
    [handleError, notify, refreshProviders, refreshStatus],
  );

  const resetSettings = useCallback(async () => {
    try {
      const result = await api.resetSettings();
      setSettings(result.settings);
      notify("Configurações restauradas.", "success");
      void refreshStatus();
    } catch (cause) {
      handleError(cause, "Não foi possível restaurar as configurações.");
    }
  }, [handleError, notify, refreshStatus]);

  const saveProviderKey = useCallback(
    async (provider: string, key: string) => {
      try {
        await api.setProviderKey(provider, key);
        notify("Chave salva no cofre local (DPAPI).", "success");
        void refreshProviders();
        void refreshStatus();
        return true;
      } catch (cause) {
        handleError(cause, "Não foi possível salvar a chave.");
        return false;
      }
    },
    [handleError, notify, refreshProviders, refreshStatus],
  );

  const removeProviderKey = useCallback(
    async (provider: string) => {
      try {
        await api.deleteProviderKey(provider);
        notify("Chave removida do cofre local.", "info");
        void refreshProviders();
        void refreshStatus();
      } catch (cause) {
        handleError(cause, "Não foi possível remover a chave.");
      }
    },
    [handleError, notify, refreshProviders, refreshStatus],
  );

  const testProvider = useCallback(
    async (provider: string) => {
      try {
        const result = await api.testProvider(provider);
        notify(result.message, result.ok ? "success" : "error");
        return result;
      } catch (cause) {
        handleError(cause, "Falha ao testar o provedor.");
        return null;
      }
    },
    [handleError, notify],
  );

  const fetchModels = useCallback(
    async (provider: string) => {
      try {
        const result = await api.providerModels(provider);
        return result.models;
      } catch (cause) {
        handleError(cause, "Não foi possível listar os modelos.");
        return [];
      }
    },
    [handleError],
  );

  const searchMemories = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed) {
        await loadMemories();
        return;
      }
      try {
        const result = await api.searchMemories(trimmed, activeIdRef.current);
        setMemories(result.memories);
      } catch (cause) {
        handleError(cause, "Falha na busca de memórias.");
      }
    },
    [handleError, loadMemories],
  );

  const addMemory = useCallback(
    async (content: string, category: MemoryRecord["category"], persistent: boolean) => {
      try {
        const result = await api.createMemory({
          content,
          category,
          persistent,
          conversation_id: activeIdRef.current,
        });
        setMemories((current) => [result.memory, ...current]);
        notify("Memória salva.", "success");
      } catch (cause) {
        handleError(cause, "Não foi possível salvar a memória.");
      }
    },
    [handleError, notify],
  );

  const updateMemory = useCallback(
    async (
      id: string,
      patch: Partial<Pick<MemoryRecord, "content" | "category" | "persistent">>,
    ) => {
      try {
        const result = await api.updateMemory(id, patch);
        setMemories((current) => current.map((memory) => (memory.id === id ? result.memory : memory)));
      } catch (cause) {
        handleError(cause, "Não foi possível atualizar a memória.");
      }
    },
    [handleError],
  );

  const deleteMemory = useCallback(
    async (id: string) => {
      try {
        await api.deleteMemory(id);
        setMemories((current) => current.filter((memory) => memory.id !== id));
      } catch (cause) {
        handleError(cause, "Não foi possível excluir a memória.");
      }
    },
    [handleError],
  );

  const handleEvent = useCallback(
    (event: WsEvent) => {
      const data = event.data ?? {};
      switch (event.type) {
        case "hello": {
          if (data.runtime) setRuntime(data.runtime as RuntimeState);
          if (data.voice) setVoice(data.voice as VoiceStatus);
          if (data.settings) setSettings(data.settings as Settings);
          break;
        }
        case "runtime.state": {
          const snapshot = data as unknown as RuntimeState;
          setRuntime(snapshot);
          setSystem((current) => (current ? { ...current, runtime: snapshot } : current));
          break;
        }
        case "voice.listening":
        case "voice.stopped":
        case "voice.started": {
          setVoice((current) => ({ ...(current ?? ({} as VoiceStatus)), ...(data as Partial<VoiceStatus>) }));
          break;
        }
        case "voice.recognized": {
          if (!manualListenRef.current && typeof data.command === "string" && data.command) {
            notify(`Ouvi: “${data.command}”`, "info");
          }
          break;
        }
        case "voice.error": {
          if (typeof data.message === "string") notify(data.message, "error");
          break;
        }
        case "voice.busy": {
          if (typeof data.message === "string") notify(data.message, "info");
          break;
        }
        case "message.created": {
          const conversationId = String(data.conversation_id ?? "");
          if (conversationId && conversationId === activeIdRef.current) {
            const message = data.message as Message | undefined;
            if (message) setMessages((current) => mergeMessages(current, [message]));
          }
          void refreshConversations();
          break;
        }
        case "conversation.updated": {
          void refreshConversations();
          break;
        }
        case "conversation.deleted": {
          if (data.conversation_id === activeIdRef.current) {
            changeActive(null);
            setMessages([]);
            setPlan([]);
            setPendingActions([]);
          }
          void refreshConversations();
          break;
        }
        case "plan.updated": {
          if (data.conversation_id === activeIdRef.current) {
            setPlan((data.plan as PlanStep[]) ?? []);
          }
          break;
        }
        case "confirmation.required": {
          const action = data.action as ActionRecord | undefined;
          if (action) {
            setPendingActions((current) => [
              action,
              ...current.filter((item) => item.id !== action.id),
            ]);
          }
          const message = data.message as Message | undefined;
          if (message && message.conversation_id === activeIdRef.current) {
            setMessages((current) => mergeMessages(current, [message]));
          }
          notify("Confirmação necessária para uma ação.", "info");
          break;
        }
        case "tool.started":
        case "tool.finished":
        case "action.blocked": {
          const action = data.action as ActionRecord | undefined;
          if (action) {
            setActions((current) => [action, ...current.filter((item) => item.id !== action.id)]);
            if (action.status === "pending") {
              setPendingActions((current) => [
                action,
                ...current.filter((item) => item.id !== action.id),
              ]);
            } else {
              setPendingActions((current) => current.filter((item) => item.id !== action.id));
            }
          }
          break;
        }
        case "assistant.error": {
          if (typeof data.message === "string") notify(data.message, "error");
          break;
        }
        case "settings.updated": {
          if (data.settings) setSettings(data.settings as Settings);
          break;
        }
        case "providers.updated": {
          void refreshProviders();
          break;
        }
        case "memory.created":
        case "memory.updated":
        case "memory.deleted": {
          void loadMemories();
          break;
        }
        default:
          break;
      }
    },
    [changeActive, loadMemories, notify, refreshConversations, refreshProviders],
  );

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let stopped = false;

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${window.location.host}/ws`);
      socket.onopen = () => {
        setConnected(true);
        socket?.send(JSON.stringify({ type: "ping", data: Date.now() }));
      };
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) reconnectTimer = window.setTimeout(connect, 2000);
      };
      socket.onerror = () => socket?.close();
      socket.onmessage = (message) => {
        try {
          handleEvent(JSON.parse(message.data) as WsEvent);
        } catch {
          /* evento malformado é ignorado */
        }
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [handleEvent]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [conversationResult, settingsResult, providerResult, toolResult, statusResult] =
          await Promise.all([
            api.conversations(),
            api.getSettings(),
            api.providers(),
            api.tools(),
            api.status(),
          ]);
        if (cancelled) return;
        setConversations(conversationResult.conversations);
        setSettings(settingsResult.settings);
        setProviders(providerResult.providers);
        setTools(toolResult.tools);
        setSystem(statusResult);
        setRuntime(statusResult.runtime);
        setVoice(statusResult.voice);
        if (conversationResult.conversations.length > 0) {
          await selectConversation(conversationResult.conversations[0].id);
        }
      } catch (cause) {
        handleError(cause, "Falha ao inicializar a interface.");
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [handleError, selectConversation]);

  useEffect(() => {
    void loadMemories();
    void refreshActions();
  }, [loadMemories, refreshActions]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refreshStatus]);

  return {
    conversations,
    activeId,
    messages,
    runtime,
    system,
    settings,
    providers,
    tools,
    plan,
    pendingActions,
    actions,
    memories,
    voice,
    connected,
    busy,
    voiceBusy,
    error,
    toast,
    selectConversation,
    sendMessage,
    cancel,
    approveAction,
    newConversation,
    deleteConversation,
    startVoice,
    stopVoice,
    listenOnce,
    stopSpeaking,
    saveSettings,
    resetSettings,
    saveProviderKey,
    removeProviderKey,
    testProvider,
    fetchModels,
    loadMemories,
    searchMemories,
    addMemory,
    updateMemory,
    deleteMemory,
    refreshStatus,
    notify,
    dismissToast,
  };
}

export type JarvisStore = ReturnType<typeof useJarvis>;
