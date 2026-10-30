import { useState } from "react";
import type { MemoryRecord } from "../types";

const CATEGORIES: Array<{ id: MemoryRecord["category"]; label: string }> = [
  { id: "preference", label: "Preferência" },
  { id: "fact", label: "Fato" },
  { id: "project", label: "Projeto" },
  { id: "contact", label: "Contato" },
  { id: "other", label: "Outro" },
];

const CATEGORY_LABEL = Object.fromEntries(
  CATEGORIES.map((category) => [category.id, category.label]),
) as Record<MemoryRecord["category"], string>;

function formatDate(value: string): string {
  try {
    return new Date(value).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
    });
  } catch {
    return "";
  }
}

export function MemoryPanel({
  memories,
  activeConversation,
  onSearch,
  onCreate,
  onUpdate,
  onDelete,
}: {
  memories: MemoryRecord[];
  activeConversation: boolean;
  onSearch: (query: string) => Promise<void>;
  onCreate: (
    content: string,
    category: MemoryRecord["category"],
    persistent: boolean,
  ) => Promise<void>;
  onUpdate: (
    id: string,
    patch: Partial<Pick<MemoryRecord, "content" | "category" | "persistent">>,
  ) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [category, setCategory] = useState<MemoryRecord["category"]>("preference");
  const [persistent, setPersistent] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [working, setWorking] = useState(false);

  const submit = async () => {
    const content = draft.trim();
    if (content.length < 2 || working) return;
    setWorking(true);
    try {
      await onCreate(content, category, persistent);
      setDraft("");
    } finally {
      setWorking(false);
    }
  };

  const saveEdit = async (memory: MemoryRecord) => {
    const content = editingText.trim();
    if (content.length < 2) return;
    setWorking(true);
    try {
      await onUpdate(memory.id, { content });
      setEditingId(null);
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="panel-scroll">
      <section className="panel-section">
        <div className="section-title">
          <span>MEMÓRIA PESSOAL</span>
          <span className="section-badge">{memories.length}</span>
        </div>
        <form
          className="memory-search"
          onSubmit={(event) => {
            event.preventDefault();
            void onSearch(query);
          }}
        >
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar nas memórias…"
            aria-label="Buscar memórias"
          />
          <button type="submit" className="filter-chip active">
            Buscar
          </button>
          {query ? (
            <button
              type="button"
              className="filter-chip"
              onClick={() => {
                setQuery("");
                void onSearch("");
              }}
            >
              Limpar
            </button>
          ) : null}
        </form>
      </section>

      <section className="panel-section memory-create">
        <div className="section-title">
          <span>NOVA MEMÓRIA</span>
        </div>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ex.: prefiro respostas curtas e diretas."
          rows={2}
          maxLength={2000}
        />
        <div className="memory-create-row">
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as MemoryRecord["category"])}
            aria-label="Categoria"
          >
            {CATEGORIES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <label className="switch-row">
            <input
              type="checkbox"
              checked={persistent}
              onChange={(event) => setPersistent(event.target.checked)}
            />
            <span>Persistente</span>
          </label>
          <button
            className="primary-button small"
            onClick={() => void submit()}
            disabled={draft.trim().length < 2 || working}
          >
            Salvar
          </button>
        </div>
        {!persistent && activeConversation ? (
          <div className="panel-hint">Memória temporária: vinculada a esta conversa e expira automaticamente.</div>
        ) : null}
      </section>

      <section className="panel-section">
        {memories.length === 0 ? (
          <div className="panel-empty small">
            Nenhuma memória encontrada. O JARVIS também salva preferências automaticamente durante as
            conversas.
          </div>
        ) : (
          <div className="memory-list">
            {memories.map((memory) => (
              <article className="memory-card" key={memory.id}>
                <div className="memory-head">
                  <span className={`memory-category category-${memory.category}`}>
                    {CATEGORY_LABEL[memory.category]}
                  </span>
                  <span className={`memory-scope ${memory.persistent ? "persistent" : "temporary"}`}>
                    {memory.persistent ? "persistente" : "temporária"}
                  </span>
                  <span className="memory-date">{formatDate(memory.updated_at)}</span>
                </div>
                {editingId === memory.id ? (
                  <div className="memory-edit">
                    <textarea
                      value={editingText}
                      onChange={(event) => setEditingText(event.target.value)}
                      rows={3}
                      maxLength={2000}
                    />
                    <div className="memory-actions">
                      <button
                        className="primary-button small"
                        onClick={() => void saveEdit(memory)}
                        disabled={working || editingText.trim().length < 2}
                      >
                        Salvar
                      </button>
                      <button className="ghost-button small" onClick={() => setEditingId(null)}>
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="memory-content">{memory.content}</p>
                )}
                <div className="memory-actions">
                  <button
                    className="ghost-button small"
                    onClick={() => {
                      setEditingId(memory.id);
                      setEditingText(memory.content);
                    }}
                  >
                    Editar
                  </button>
                  <button
                    className="ghost-button small"
                    onClick={() => void onUpdate(memory.id, { persistent: !memory.persistent })}
                    disabled={working}
                    title={
                      memory.persistent
                        ? "Tornar temporária (expira automaticamente)"
                        : "Tornar persistente"
                    }
                  >
                    {memory.persistent ? "Tornar temporária" : "Tornar persistente"}
                  </button>
                  <button
                    className="danger-button small"
                    onClick={() => {
                      if (window.confirm("Excluir esta memória permanentemente?")) {
                        void onDelete(memory.id);
                      }
                    }}
                    disabled={working}
                  >
                    Excluir
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
