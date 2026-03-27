import { create } from "zustand";
import type { DocumentationResult, PipelineStage } from "../types/api";
import type { ApprovalStatus, SOAPSectionKey, SOAPSectionState, EditHistoryEntry } from "../types/soap";

interface SessionState {
  // Recording
  isRecording: boolean;
  isPaused: boolean;
  recordingDuration: number;
  audioLevel: number;

  // Processing
  isProcessing: boolean;
  pipelineStages: PipelineStage[];
  currentStage: string | null;

  // Results
  transcript: string;
  documentation: DocumentationResult | null;
  soapSections: Record<SOAPSectionKey, SOAPSectionState>;

  // Actions — Recording
  startRecording: () => void;
  stopRecording: () => void;
  pauseRecording: () => void;
  resumeRecording: () => void;
  setRecordingDuration: (duration: number) => void;
  setAudioLevel: (level: number) => void;

  // Actions — Processing
  setProcessing: (processing: boolean) => void;
  setPipelineStages: (stages: PipelineStage[]) => void;
  setCurrentStage: (stage: string | null) => void;

  // Actions — Results
  setTranscript: (transcript: string) => void;
  setDocumentation: (doc: DocumentationResult) => void;
  updateSOAPSection: (key: SOAPSectionKey, content: string) => void;
  approveSOAPSection: (key: SOAPSectionKey) => void;
  rejectSOAPSection: (key: SOAPSectionKey) => void;
  startEditingSOAP: (key: SOAPSectionKey) => void;
  cancelEditingSOAP: (key: SOAPSectionKey) => void;
  restoreSOAPSection: (key: SOAPSectionKey, historyIndex: number) => void;

  // Reset
  resetSession: () => void;
}

const createEmptySOAPSection = (): SOAPSectionState => ({
  content: "",
  originalContent: "",
  status: "pending",
  isEditing: false,
  editHistory: [],
});

const initialSOAPSections: Record<SOAPSectionKey, SOAPSectionState> = {
  chiefComplaint: createEmptySOAPSection(),
  clinicalDetails: createEmptySOAPSection(),
  subjective: createEmptySOAPSection(),
  objective: createEmptySOAPSection(),
  assessment: createEmptySOAPSection(),
  plan: createEmptySOAPSection(),
};

const addHistoryEntry = (
  section: SOAPSectionState,
  newContent: string,
  action: EditHistoryEntry["action"]
): SOAPSectionState["editHistory"] => [
  ...section.editHistory,
  {
    timestamp: new Date().toISOString(),
    previousContent: section.content,
    newContent,
    action,
  },
];

export const useSessionStore = create<SessionState>()((set) => ({
  // Initial state
  isRecording: false,
  isPaused: false,
  recordingDuration: 0,
  audioLevel: 0,
  isProcessing: false,
  pipelineStages: [],
  currentStage: null,
  transcript: "",
  documentation: null,
  soapSections: { ...initialSOAPSections },

  // Recording actions
  startRecording: () => set({ isRecording: true, isPaused: false, recordingDuration: 0 }),
  stopRecording: () => set({ isRecording: false, isPaused: false }),
  pauseRecording: () => set({ isPaused: true }),
  resumeRecording: () => set({ isPaused: false }),
  setRecordingDuration: (recordingDuration) => set({ recordingDuration }),
  setAudioLevel: (audioLevel) => set({ audioLevel }),

  // Processing actions
  setProcessing: (isProcessing) => set({ isProcessing }),
  setPipelineStages: (pipelineStages) => set({ pipelineStages }),
  setCurrentStage: (currentStage) => set({ currentStage }),

  // Results actions
  setTranscript: (transcript) => set({ transcript }),
  setDocumentation: (doc) =>
    set({
      documentation: doc,
      soapSections: {
        chiefComplaint: { ...createEmptySOAPSection(), content: doc.chiefComplaint, originalContent: doc.chiefComplaint },
        clinicalDetails: { ...createEmptySOAPSection(), content: doc.clinicalDetails, originalContent: doc.clinicalDetails },
        subjective: { ...createEmptySOAPSection(), content: doc.subjective, originalContent: doc.subjective },
        objective: { ...createEmptySOAPSection(), content: doc.objective, originalContent: doc.objective },
        assessment: { ...createEmptySOAPSection(), content: doc.assessment, originalContent: doc.assessment },
        plan: { ...createEmptySOAPSection(), content: doc.plan, originalContent: doc.plan },
      },
    }),

  updateSOAPSection: (key, content) =>
    set((state) => ({
      soapSections: {
        ...state.soapSections,
        [key]: {
          ...state.soapSections[key],
          content,
          isEditing: false,
          editHistory: addHistoryEntry(state.soapSections[key], content, "edit"),
        },
      },
    })),

  approveSOAPSection: (key) =>
    set((state) => ({
      soapSections: {
        ...state.soapSections,
        [key]: {
          ...state.soapSections[key],
          status: "approved" as ApprovalStatus,
          isEditing: false,
          editHistory: addHistoryEntry(state.soapSections[key], state.soapSections[key].content, "approve"),
        },
      },
    })),

  rejectSOAPSection: (key) =>
    set((state) => ({
      soapSections: {
        ...state.soapSections,
        [key]: {
          ...state.soapSections[key],
          status: "rejected" as ApprovalStatus,
          isEditing: false,
          editHistory: addHistoryEntry(state.soapSections[key], state.soapSections[key].content, "reject"),
        },
      },
    })),

  startEditingSOAP: (key) =>
    set((state) => ({
      soapSections: {
        ...state.soapSections,
        [key]: { ...state.soapSections[key], isEditing: true },
      },
    })),

  cancelEditingSOAP: (key) =>
    set((state) => ({
      soapSections: {
        ...state.soapSections,
        [key]: { ...state.soapSections[key], isEditing: false },
      },
    })),

  restoreSOAPSection: (key, historyIndex) =>
    set((state) => {
      const entry = state.soapSections[key].editHistory[historyIndex];
      if (!entry) return state;
      return {
        soapSections: {
          ...state.soapSections,
          [key]: {
            ...state.soapSections[key],
            content: entry.previousContent,
            status: "pending" as ApprovalStatus,
            isEditing: false,
            editHistory: addHistoryEntry(state.soapSections[key], entry.previousContent, "restore"),
          },
        },
      };
    }),

  resetSession: () =>
    set({
      isRecording: false,
      isPaused: false,
      recordingDuration: 0,
      audioLevel: 0,
      isProcessing: false,
      pipelineStages: [],
      currentStage: null,
      transcript: "",
      documentation: null,
      soapSections: { ...initialSOAPSections },
    }),
}));
