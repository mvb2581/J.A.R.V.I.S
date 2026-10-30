import type { JarvisStore } from "../useJarvis";
import { ActionsPanel } from "./ActionsPanel";
import { MemoryPanel } from "./MemoryPanel";
import { PlanPanel } from "./PlanPanel";
import { SettingsPanel } from "./SettingsPanel";
import { SystemPanel } from "./SystemPanel";

export type RightTab = "system" | "plan" | "actions" | "memory" | "settings";

const TABS: Array<{ id: RightTab; label: string }> = [
  { id: "system", label: "Sistema" },
  { id: "plan", label: "Plano" },
  { id: "actions", label: "Ações" },
  { id: "memory", label: "Memória" },
  { id: "settings", label: "Config" },
];

export function RightPanel({
  store,
  tab,
  onTabChange,
}: {
  store: JarvisStore;
  tab: RightTab;
  onTabChange: (tab: RightTab) => void;
}) {
  const pendingCount = store.pendingActions.length;
  const planDone = store.plan.filter((step) => step.status === "done").length;
  const planBadge = store.plan.length > 0 ? `${planDone}/${store.plan.length}` : null;

  return (
    <aside className="right-panel">
      <nav className="right-tabs" aria-label="Painéis do sistema">
        {TABS.map((item) => (
          <button
            key={item.id}
            className={`right-tab ${tab === item.id ? "active" : ""}`}
            onClick={() => onTabChange(item.id)}
          >
            <span>{item.label}</span>
            {item.id === "actions" && pendingCount > 0 ? (
              <span className="tab-badge alert">{pendingCount}</span>
            ) : null}
            {item.id === "plan" && planBadge ? (
              <span className="tab-badge">{planBadge}</span>
            ) : null}
            {item.id === "memory" && store.memories.length > 0 ? (
              <span className="tab-badge">{store.memories.length}</span>
            ) : null}
          </button>
        ))}
      </nav>

      <div className="right-content">
        {tab === "system" ? (
          <SystemPanel system={store.system} runtime={store.runtime} voice={store.voice} />
        ) : null}
        {tab === "plan" ? (
          <PlanPanel plan={store.plan} activeConversation={Boolean(store.activeId)} />
        ) : null}
        {tab === "actions" ? (
          <ActionsPanel
            actions={store.actions}
            activeConversation={Boolean(store.activeId)}
            onApprove={store.approveAction}
            busy={store.busy}
          />
        ) : null}
        {tab === "memory" ? (
          <MemoryPanel
            memories={store.memories}
            activeConversation={Boolean(store.activeId)}
            onSearch={store.searchMemories}
            onCreate={store.addMemory}
            onUpdate={store.updateMemory}
            onDelete={store.deleteMemory}
          />
        ) : null}
        {tab === "settings" ? (
          <SettingsPanel
            settings={store.settings}
            providers={store.providers}
            onSave={store.saveSettings}
            onReset={store.resetSettings}
            onSaveKey={store.saveProviderKey}
            onRemoveKey={store.removeProviderKey}
            onTestProvider={store.testProvider}
            onFetchModels={store.fetchModels}
          />
        ) : null}
      </div>
    </aside>
  );
}
