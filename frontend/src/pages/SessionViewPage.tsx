import { useParams } from "react-router-dom";
import { Header } from "../components/layout/Header";
import { ResultsContainer } from "../components/soap/ResultsContainer";
import { ExportBar } from "../components/voice/ExportBar";
import { ConversationPanel } from "../components/conversation/ConversationPanel";
import { ConversationToggle } from "../components/conversation/ConversationToggle";
import { useConversationStore } from "../stores/conversationStore";
import { GlassCard } from "../components/ui/GlassCard";
import { Badge } from "../components/ui/Badge";

export default function SessionViewPage() {
  const { id } = useParams<{ id: string }>();
  const isConvOpen = useConversationStore((s) => s.isOpen);

  return (
    <>
      <Header
        title={`Session ${id}`}
        subtitle="View encounter details"
        actions={
          <ExportBar
            onExportJSON={() => {}}
            onExportPDF={() => {}}
            onExportFHIR={() => {}}
            onPushEHR={() => {}}
          />
        }
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-3xl space-y-6">
            {/* Session info */}
            <GlassCard className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                    Session Details
                  </h3>
                  <p className="text-xs text-[var(--text-muted)]">
                    ID: {id}
                  </p>
                </div>
                <Badge variant="success">Completed</Badge>
              </div>
            </GlassCard>

            {/* SOAP results */}
            <ResultsContainer sessionId={id} />
          </div>
        </div>

        {/* Conversation sidebar */}
        {isConvOpen && (
          <div className="w-96">
            <ConversationPanel sessionId={id} />
          </div>
        )}
      </div>
      <ConversationToggle />
    </>
  );
}
