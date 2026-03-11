import { useReducer, useCallback } from 'react';
import { initialState } from '../store/appState';
import type { AppState, ViewName, InputMode } from '../store/appState';
import type { Analysis, TranscriptEntry, ScreenshotEntry, BridgeState, LiveState as LiveStateAPI } from '../types/electron';

// ─── Action Types ─────────────────────────────────────────────────────────────

type Action =
  | { type: 'SET_ACTIVE_VIEW'; view: ViewName }
  | { type: 'SET_STATUS'; message: string }
  | { type: 'SET_PERMISSION_WARNING'; message: string }
  | { type: 'SET_CONFIRMATION_MESSAGE'; message: string }
  | { type: 'SET_CAPTURE_IN_FLIGHT'; value: boolean }
  | { type: 'SET_ANALYSIS'; analysis: Analysis | null }
  | { type: 'SET_AI_REVEALED'; value: boolean }
  | { type: 'SET_FLAG_MODE'; value: boolean }
  | { type: 'SET_DOCTOR_DRAFT'; value: string }
  | { type: 'SET_FLAG_DRAFT'; value: string }
  | { type: 'SET_DEMO_MODE'; value: boolean }
  | { type: 'SET_HOTKEY'; hotkey: string }
  | { type: 'SET_SESSION_ID'; id: string }
  | { type: 'APPLY_SNAPSHOT'; snapshot: BridgeState }
  | { type: 'APPLY_LIVE_SNAPSHOT'; snapshot: LiveStateAPI }
  | { type: 'SET_LIVE_CONNECTED'; connected: boolean; message: string }
  | { type: 'SET_LIVE_PHASE'; phase: string }
  | { type: 'SET_LIVE_MIC_ACTIVE'; active: boolean }
  | { type: 'APPEND_TRANSCRIPT'; entry: TranscriptEntry }
  | { type: 'SET_TRANSCRIPT'; entries: TranscriptEntry[] }
  | { type: 'UPSERT_SCREENSHOT'; entry: ScreenshotEntry }
  | { type: 'SET_SCREENSHOTS'; entries: ScreenshotEntry[] }
  | { type: 'SET_INPUT_MODE'; mode: InputMode }
  | { type: 'ANALYSIS_EVENT'; payload: AnalysisEventPayload };

interface AnalysisEventPayload {
  finding: string;
  confidence: string;
  image_hash: string;
  recommendation?: string;
  specialist_flags?: string[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function upsertScreenshot(history: ScreenshotEntry[], entry: ScreenshotEntry): ScreenshotEntry[] {
  const requestId = entry.request_id;
  if (!requestId) {
    return [entry, ...history].slice(0, 5);
  }
  const index = history.findIndex((item) => item.request_id === requestId);
  let updated: ScreenshotEntry[];
  if (index === -1) {
    updated = [entry, ...history];
  } else {
    updated = [...history];
    updated[index] = entry;
    if (index !== 0) {
      updated.unshift(updated.splice(index, 1)[0]);
    }
  }
  return updated.slice(0, 5);
}

// ─── Reducer ─────────────────────────────────────────────────────────────────

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_ACTIVE_VIEW':
      return { ...state, activeView: action.view };

    case 'SET_STATUS':
      return { ...state, statusMessage: action.message };

    case 'SET_PERMISSION_WARNING':
      return { ...state, permissionWarning: action.message };

    case 'SET_CONFIRMATION_MESSAGE':
      return { ...state, confirmationMessage: action.message };

    case 'SET_CAPTURE_IN_FLIGHT':
      return { ...state, captureInFlight: action.value };

    case 'SET_ANALYSIS':
      return { ...state, analysis: action.analysis };

    case 'SET_AI_REVEALED':
      return { ...state, aiRevealed: action.value };

    case 'SET_FLAG_MODE':
      return { ...state, flagMode: action.value };

    case 'SET_DOCTOR_DRAFT':
      return { ...state, doctorDraft: action.value };

    case 'SET_FLAG_DRAFT':
      return { ...state, flagDraft: action.value };

    case 'SET_DEMO_MODE':
      return { ...state, demoMode: action.value };

    case 'SET_HOTKEY':
      return { ...state, hotkey: action.hotkey };

    case 'SET_SESSION_ID':
      return { ...state, sessionId: action.id };

    case 'SET_INPUT_MODE':
      return { ...state, inputMode: action.mode };

    case 'APPLY_SNAPSHOT':
      return {
        ...state,
        sessionId: action.snapshot.session_id || '',
        statusMessage: action.snapshot.status_message || 'Ready',
        permissionWarning: action.snapshot.permission_warning || '',
        confirmationMessage: action.snapshot.confirmation_message || '',
        analysis: action.snapshot.analysis || null,
        demoMode: Boolean(action.snapshot.demo_mode),
        aiRevealed: false,
      };

    case 'APPLY_LIVE_SNAPSHOT':
      return {
        ...state,
        live: {
          connected: Boolean(action.snapshot.live?.connected),
          message: action.snapshot.live?.message || state.live.message,
          phase: action.snapshot.live?.phase || '',
          micActive: Boolean(action.snapshot.live?.mic_active),
        },
        transcriptEntries: action.snapshot.transcript_entries || [],
        screenshotHistory: action.snapshot.screenshot_history || [],
        sessionId: action.snapshot.session_id || state.sessionId,
      };

    case 'SET_LIVE_CONNECTED':
      return {
        ...state,
        live: {
          ...state.live,
          connected: action.connected,
          message: action.message,
          phase: action.connected ? state.live.phase : '',
          micActive: action.connected ? state.live.micActive : false,
        },
      };

    case 'SET_LIVE_PHASE':
      return { ...state, live: { ...state.live, phase: action.phase } };

    case 'SET_LIVE_MIC_ACTIVE':
      return { ...state, live: { ...state.live, micActive: action.active } };

    case 'APPEND_TRANSCRIPT': {
      const entries = [...state.transcriptEntries, action.entry].slice(-100);
      return { ...state, transcriptEntries: entries };
    }

    case 'SET_TRANSCRIPT':
      return { ...state, transcriptEntries: action.entries };

    case 'UPSERT_SCREENSHOT':
      return { ...state, screenshotHistory: upsertScreenshot(state.screenshotHistory, action.entry) };

    case 'SET_SCREENSHOTS':
      return { ...state, screenshotHistory: action.entries };

    case 'ANALYSIS_EVENT': {
      const analysis: Analysis = {
        finding: action.payload.finding,
        confidence: action.payload.confidence,
        image_hash: action.payload.image_hash,
        recommendation: action.payload.recommendation || '',
        specialist_flags: action.payload.specialist_flags || [],
      };
      return {
        ...state,
        analysis,
        statusMessage: 'Analysis ready',
        captureInFlight: false,
        aiRevealed: false,
        flagMode: false,
        activeView: 'Insights',
      };
    }

    default:
      return state;
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAppState() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const setActiveView = useCallback((view: ViewName) => dispatch({ type: 'SET_ACTIVE_VIEW', view }), []);
  const setStatus = useCallback((message: string) => dispatch({ type: 'SET_STATUS', message }), []);
  const setPermissionWarning = useCallback((message: string) => dispatch({ type: 'SET_PERMISSION_WARNING', message }), []);
  const setConfirmationMessage = useCallback((message: string) => dispatch({ type: 'SET_CONFIRMATION_MESSAGE', message }), []);
  const setCaptureInFlight = useCallback((value: boolean) => dispatch({ type: 'SET_CAPTURE_IN_FLIGHT', value }), []);
  const setAnalysis = useCallback((analysis: Analysis | null) => dispatch({ type: 'SET_ANALYSIS', analysis }), []);
  const setAiRevealed = useCallback((value: boolean) => dispatch({ type: 'SET_AI_REVEALED', value }), []);
  const setFlagMode = useCallback((value: boolean) => dispatch({ type: 'SET_FLAG_MODE', value }), []);
  const setDoctorDraft = useCallback((value: string) => dispatch({ type: 'SET_DOCTOR_DRAFT', value }), []);
  const setFlagDraft = useCallback((value: string) => dispatch({ type: 'SET_FLAG_DRAFT', value }), []);
  const setDemoMode = useCallback((value: boolean) => dispatch({ type: 'SET_DEMO_MODE', value }), []);
  const setHotkey = useCallback((hotkey: string) => dispatch({ type: 'SET_HOTKEY', hotkey }), []);
  const setSessionId = useCallback((id: string) => dispatch({ type: 'SET_SESSION_ID', id }), []);
  const setInputMode = useCallback((mode: InputMode) => dispatch({ type: 'SET_INPUT_MODE', mode }), []);
  const applySnapshot = useCallback((snapshot: BridgeState) => dispatch({ type: 'APPLY_SNAPSHOT', snapshot }), []);
  const applyLiveSnapshot = useCallback((snapshot: LiveStateAPI) => dispatch({ type: 'APPLY_LIVE_SNAPSHOT', snapshot }), []);

  const setLiveConnected = useCallback((connected: boolean, message: string) =>
    dispatch({ type: 'SET_LIVE_CONNECTED', connected, message }), []);
  const setLivePhase = useCallback((phase: string) => dispatch({ type: 'SET_LIVE_PHASE', phase }), []);
  const setLiveMicActive = useCallback((active: boolean) => dispatch({ type: 'SET_LIVE_MIC_ACTIVE', active }), []);

  const appendTranscript = useCallback((role: TranscriptEntry['role'], text: string) => {
    const cleaned = text.trim();
    if (!cleaned) return;
    dispatch({ type: 'APPEND_TRANSCRIPT', entry: { role, text: cleaned } });
  }, []);

  const setTranscript = useCallback((entries: TranscriptEntry[]) => dispatch({ type: 'SET_TRANSCRIPT', entries }), []);
  const upsertScreenshot = useCallback((entry: ScreenshotEntry) => dispatch({ type: 'UPSERT_SCREENSHOT', entry }), []);
  const setScreenshots = useCallback((entries: ScreenshotEntry[]) => dispatch({ type: 'SET_SCREENSHOTS', entries }), []);

  const applyAnalysisEvent = useCallback((payload: AnalysisEventPayload) =>
    dispatch({ type: 'ANALYSIS_EVENT', payload }), []);

  return {
    state,
    dispatch,
    actions: {
      setActiveView,
      setStatus,
      setPermissionWarning,
      setConfirmationMessage,
      setCaptureInFlight,
      setAnalysis,
      setAiRevealed,
      setFlagMode,
      setDoctorDraft,
      setFlagDraft,
      setDemoMode,
      setHotkey,
      setSessionId,
      setInputMode,
      applySnapshot,
      applyLiveSnapshot,
      setLiveConnected,
      setLivePhase,
      setLiveMicActive,
      appendTranscript,
      setTranscript,
      upsertScreenshot,
      setScreenshots,
      applyAnalysisEvent,
    },
  };
}

export type AppActions = ReturnType<typeof useAppState>['actions'];
