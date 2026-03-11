import type { Analysis, TranscriptEntry, ScreenshotEntry } from '../types/electron';

export type ViewName = 'Insights' | 'Measure' | 'Compare' | 'QA' | 'Transcript';
export type InputMode = 'notes' | 'transcript';

export interface LiveState {
  connected: boolean;
  message: string;
  phase: string;
  micActive: boolean;
}

export interface AppState {
  sessionId: string;
  hotkey: string;
  windowMode: 'orb' | 'bar';
  activeView: ViewName;
  statusMessage: string;
  permissionWarning: string;
  confirmationMessage: string;
  analysis: Analysis | null;
  aiRevealed: boolean;
  flagMode: boolean;
  doctorDraft: string;
  flagDraft: string;
  live: LiveState;
  transcriptEntries: TranscriptEntry[];
  screenshotHistory: ScreenshotEntry[];
  demoMode: boolean;
  captureInFlight: boolean;
  inputMode: InputMode;
}

export const initialState: AppState = {
  sessionId: '',
  hotkey: 'Cmd+Shift+R',
  windowMode: 'orb',
  activeView: 'Insights',
  statusMessage: 'Ready',
  permissionWarning: '',
  confirmationMessage: '',
  analysis: null,
  aiRevealed: false,
  flagMode: false,
  doctorDraft: '',
  flagDraft: '',
  live: {
    connected: false,
    message: 'Gemini Live unavailable',
    phase: '',
    micActive: false,
  },
  transcriptEntries: [],
  screenshotHistory: [],
  demoMode: false,
  captureInFlight: false,
  inputMode: 'notes',
};
