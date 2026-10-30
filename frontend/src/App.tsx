import { useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { RightPanel, type RightTab } from "./components/RightPanel";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { useJarvis } from "./useJarvis";

export default function App() {
  const store = useJarvis();
  const [tab, setTab] = useState<RightTab>("system");
  const [panelOpen, setPanelOpen] = useState(false);

  const toggleWake = () => {
    if (store.voice?.wake_mode_active) {
      void store.stopVoice();
    } else {
      void store.startVoice();
    }
  };

  const stopEverything = () => {
    void store.cancel();
    void store.stopSpeaking();
  };

  return (
    <div className="app-shell">
      <TopBar
        runtime={store.runtime}
        voice={store.voice}
        settings={store.settings}
        connected={store.connected}
        voiceBusy={store.voiceBusy}
        onToggleWake={toggleWake}
        onListen={() => void store.listenOnce()}
        onStop={stopEverything}
        onStopSpeaking={() => void store.stopSpeaking()}
        onOpenSettings={() => {
          setTab("settings");
          setPanelOpen(true);
        }}
      />

      <div className="app-body">
        <Sidebar
          conversations={store.conversations}
          activeId={store.activeId}
          connected={store.connected}
          onSelect={(id) => void store.selectConversation(id)}
          onNew={() => void store.newConversation()}
          onDelete={(id) => void store.deleteConversation(id)}
        />

        <ChatPanel
          messages={store.messages}
          runtime={store.runtime}
          busy={store.busy}
          voiceBusy={store.voiceBusy}
          pendingActions={store.pendingActions}
          plan={store.plan}
          onSend={(text) => void store.sendMessage(text)}
          onApprove={(actionId, approve) => void store.approveAction(actionId, approve)}
          onListen={() => void store.listenOnce()}
          onCancel={() => void store.cancel()}
        />

        <div className={`right-panel-wrap ${panelOpen ? "open" : ""}`}>
          <RightPanel
            store={store}
            tab={tab}
            onTabChange={(next) => {
              setTab(next);
              setPanelOpen(true);
            }}
          />
        </div>
      </div>

      <button
        className="panel-toggle"
        onClick={() => setPanelOpen((current) => !current)}
        aria-label="Mostrar ou ocultar painel lateral"
      >
        {panelOpen ? "FECHAR PAINEL" : "PAINEL"}
      </button>

      {store.toast ? (
        <div className={`toast toast-${store.toast.kind}`} role="status">
          <span className={`status-dot ${store.toast.kind === "error" ? "fail" : "ok"}`} />
          {store.toast.message}
          <button
            className="toast-close"
            onClick={store.dismissToast}
            aria-label="Fechar notificação"
          >
            ×
          </button>
        </div>
      ) : null}
    </div>
  );
}
