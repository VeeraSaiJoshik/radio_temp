/* ═══════════════════════════════════════════════════════
   Radiology Copilot — Renderer App
   Liquid Glass UI with orb ↔ bar mode toggle
   ═══════════════════════════════════════════════════════ */

// Global types (copilotDesktop, LiveMediaController, etc.) are declared in renderer.d.ts.

// App-local type aliases that reference the shared renderer.d.ts types:
type AnalysisResult = RendererAnalysisResult;
type TranscriptEntry = RendererTranscriptEntry;
type ScreenshotEntry = RendererScreenshotEntry;
type LiveCommand = RendererLiveCommand;
type AppEvent = RendererAppEvent;

interface LiveState {
  connected: boolean;
  message: string;
  phase: string;
  micActive: boolean;
}

interface AppState {
  sessionId: string;
  hotkey: string;
  activeView: string;
  statusMessage: string;
  permissionWarning: string;
  confirmationMessage: string;
  analysis: AnalysisResult | null;
  aiRevealed: boolean;
  flagMode: boolean;
  doctorDraft: string;
  flagDraft: string;
  live: LiveState;
  transcriptEntries: TranscriptEntry[];
  screenshotHistory: ScreenshotEntry[];
  demoMode: boolean;
  captureInFlight: boolean;
  uiMode: 'orb' | 'bar';
  panelExpanded: boolean;
  inputMode: 'notes' | 'transcript';
  bannerVisible: boolean;
}

interface AppElements {
  overlayRoot: HTMLElement;
  heroTitle: HTMLElement;
  heroBody: HTMLElement;
  statusBanner: HTMLElement;
  liveBanner: HTMLElement;
  warningBanner: HTMLElement;
  confidenceBadge: HTMLElement;
  imageHash: HTMLElement;
  doctorInput: HTMLTextAreaElement;
  revealButton: HTMLButtonElement;
  captureButton: HTMLButtonElement;
  analysisCard: HTMLElement;
  analysisState: HTMLElement;
  analysisText: HTMLElement;
  recommendationText: HTMLElement;
  specialistFlags: HTMLElement;
  agreeButton: HTMLButtonElement;
  disagreeButton: HTMLButtonElement;
  flagForm: HTMLElement;
  flagInput: HTMLInputElement;
  submitFlagButton: HTMLButtonElement;
  measureSummary: HTMLElement;
  compareDoctor: HTMLElement;
  compareAi: HTMLElement;
  qaMeta: HTMLElement;
  qaImage: HTMLImageElement;
  qaEmpty: HTMLElement;
  qaHistory: HTMLElement;
  transcriptLog: HTMLElement;
  askInput: HTMLInputElement;
  inputBar: HTMLElement;
  sendButton: HTMLButtonElement;
  micButton: HTMLButtonElement;
  miniOrb: HTMLElement;
  askButton: HTMLElement;
  listeningIndicator: HTMLElement;
  simulateButton: HTMLButtonElement;
  contentPanel: HTMLElement;
  panelColumn: HTMLElement;
}


const state: AppState = {
  sessionId: '',
  hotkey: 'Cmd+Shift+R',
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
    micActive: false
  },
  transcriptEntries: [],
  screenshotHistory: [],
  demoMode: false,
  captureInFlight: false,
  uiMode: 'orb',
  panelExpanded: true,
  inputMode: 'notes',
  bannerVisible: false
};

const elements: Partial<AppElements> = {};
let liveMedia: LiveMediaControllerClass | null = null;
let ringLeaveTimer: ReturnType<typeof setTimeout> | null = null;
let lastAppliedWindowMode = '';

function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

/* ═══════════════════════════════════════════════════════
   TEXT HELPERS
   ═══════════════════════════════════════════════════════ */

function titleForAnalysis(): string {
  if (!state.analysis) {
    return 'Capture a screen to start the next read.';
  }
  if (state.aiRevealed) {
    return 'AI analysis revealed.';
  }
  return 'Your read is staged. Reveal the model when ready.';
}

function bodyForAnalysis(): string {
  if (state.permissionWarning) {
    return state.permissionWarning;
  }
  if (!state.analysis) {
    return 'The overlay stays quiet until you capture the workstation and write your interpretation.';
  }
  if (!state.aiRevealed) {
    return 'Write your interpretation first, then reveal the model output to avoid anchoring bias.';
  }
  return state.analysis.recommendation || 'No recommended action was returned for this read.';
}

function latestBannerText(): string {
  return state.confirmationMessage || state.statusMessage || 'Ready';
}

function syncWindowMode(): void {
  if (!window.copilotDesktop || state.uiMode === lastAppliedWindowMode) {
    return;
  }

  lastAppliedWindowMode = state.uiMode;
  void window.copilotDesktop.setWindowMode(state.uiMode).catch(() => {
    lastAppliedWindowMode = '';
  });
}

function collapseOverlay(): void {
  state.uiMode = 'orb';
  render();
}

/* ═══════════════════════════════════════════════════════
   RENDER
   ═══════════════════════════════════════════════════════ */

function renderViewButtons(): void {
  document.querySelectorAll<HTMLElement>('.pill[data-view]').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === state.activeView);
  });
  document.querySelectorAll<HTMLElement>('.view').forEach((view) => {
    const name = view.id.replace('-view', '');
    const normalized = name.charAt(0).toUpperCase() + name.slice(1);
    view.classList.toggle('active', normalized === state.activeView);
  });
}

function renderFlags(): void {
  elements.specialistFlags!.replaceChildren();
  const flags = state.analysis?.specialist_flags || [];
  if (!flags.length) {
    const empty = document.createElement('span');
    empty.className = 'meta-copy';
    empty.textContent = 'No specialist flags';
    elements.specialistFlags!.appendChild(empty);
    return;
  }

  flags.forEach((flag) => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = flag;
    elements.specialistFlags!.appendChild(tag);
  });
}

function renderTranscript(): void {
  elements.transcriptLog!.replaceChildren();
  if (!state.transcriptEntries.length) {
    const empty = document.createElement('div');
    empty.className = 'transcript-entry system';
    empty.textContent = 'Gemini Live messages will appear here once the session is connected.';
    elements.transcriptLog!.appendChild(empty);
    return;
  }

  state.transcriptEntries.forEach((entry) => {
    const row = document.createElement('div');
    row.className = `transcript-entry ${entry.role}`;
    row.textContent = `${entry.role === 'assistant' ? 'Gemini' : entry.role === 'system' ? 'System' : 'You'}: ${entry.text}`;
    elements.transcriptLog!.appendChild(row);
  });
  elements.transcriptLog!.scrollTop = elements.transcriptLog!.scrollHeight;
}

function renderScreenshots(): void {
  const latest = state.screenshotHistory[0];
  elements.qaHistory!.replaceChildren();

  if (!latest) {
    elements.qaMeta!.textContent = 'No screenshot captured yet.';
    elements.qaImage!.classList.add('hidden');
    elements.qaEmpty!.classList.remove('hidden');
  } else {
    elements.qaMeta!.textContent = `${latest.reason || 'Gemini requested a screenshot'} · ${latest.image_hash || 'hash pending'}`;
    if (latest.image_b64) {
      elements.qaImage!.src = `data:image/jpeg;base64,${latest.image_b64}`;
      elements.qaImage!.classList.remove('hidden');
      elements.qaEmpty!.classList.add('hidden');
    } else {
      elements.qaImage!.classList.add('hidden');
      elements.qaEmpty!.classList.remove('hidden');
    }
  }

  if (!state.screenshotHistory.length) {
    const empty = document.createElement('div');
    empty.className = 'history-item';
    empty.textContent = 'No screenshot tool activity yet.';
    elements.qaHistory!.appendChild(empty);
    return;
  }

  state.screenshotHistory.forEach((entry) => {
    const item = document.createElement('div');
    item.className = 'history-item';
    const reason = entry.reason || 'Screenshot event';
    const backendStatus = entry.backend_status || entry.status || 'pending';
    item.textContent = `${reason} · ${backendStatus} · ${entry.image_hash || 'hash pending'}`;
    elements.qaHistory!.appendChild(item);
  });
}

function renderContentPanel(): void {
  const panel = elements.contentPanel!;

  if (panel.classList.contains('content-collapsed')) {
    panel.classList.remove('content-collapsed');
    panel.classList.add('fade-in');
    panel.addEventListener('animationend', () => panel.classList.remove('fade-in'), {
      once: true
    });
  }
}

function renderSendButton(): void {
  const hasText = elements.askInput!.value.trim().length > 0;
  elements.sendButton!.classList.toggle('visible', hasText);
}

function renderAnalysis(): void {
  const analysis = state.analysis;
  elements.heroTitle!.textContent = titleForAnalysis();
  elements.heroBody!.textContent = bodyForAnalysis();
  elements.statusBanner!.textContent = latestBannerText();
  elements.liveBanner!.textContent = state.live.phase || state.live.message;
  elements.warningBanner!.textContent = state.permissionWarning;
  elements.warningBanner!.classList.toggle('hidden', !state.permissionWarning);

  elements.doctorInput!.value = state.doctorDraft;
  elements.flagInput!.value = state.flagDraft;
  elements.captureButton!.disabled = state.captureInFlight;
  elements.revealButton!.disabled = !analysis;
  elements.disagreeButton!.disabled = !analysis || !state.aiRevealed;
  elements.agreeButton!.disabled = !analysis || !state.aiRevealed;
  elements.micButton!.textContent = state.live.micActive ? 'Stop Mic' : 'Mic';
  elements.micButton!.disabled = !state.live.connected;

  // Listening indicator
  elements.listeningIndicator!.classList.toggle('hidden', !state.live.micActive);

  // Simulate button (only in demo mode)
  elements.simulateButton!.classList.toggle('hidden', !state.demoMode);

  if (!analysis) {
    elements.analysisCard!.classList.add('hidden');
    elements.confidenceBadge!.classList.add('hidden');
    elements.imageHash!.textContent = 'hash pending';
    elements.measureSummary!.textContent =
      'Once a read is captured, the latest finding and recommendation will be staged here for structured measurements.';
    elements.compareDoctor!.textContent = state.doctorDraft || 'No read drafted yet.';
    elements.compareAi!.textContent = 'No AI analysis loaded.';
    return;
  }

  elements.imageHash!.textContent = analysis.image_hash;
  elements.confidenceBadge!.classList.remove('hidden');
  elements.confidenceBadge!.textContent = analysis.confidence.toUpperCase();
  elements.analysisCard!.classList.remove('hidden');
  elements.analysisState!.textContent = state.aiRevealed ? 'Revealed' : 'Hidden';
  elements.analysisText!.textContent = state.aiRevealed
    ? analysis.finding
    : 'AI analysis is hidden until you commit your own interpretation.';
  elements.recommendationText!.textContent = state.aiRevealed
    ? analysis.recommendation || 'No recommended action returned.'
    : 'Reveal the analysis to inspect the recommendation.';
  renderFlags();

  elements.flagForm!.classList.toggle('hidden', !state.flagMode || !state.aiRevealed);
  elements.measureSummary!.textContent = analysis.recommendation || analysis.finding;
  elements.compareDoctor!.textContent = state.doctorDraft || 'No doctor read entered yet.';
  elements.compareAi!.textContent = state.aiRevealed
    ? analysis.finding
    : 'Still hidden behind the diagnosis-first gate.';
}

function renderMode(): void {
  const orbMode = state.uiMode === 'orb';
  elements.overlayRoot!.classList.toggle('orb-mode', orbMode);
  elements.overlayRoot!.classList.toggle('bar-mode', !orbMode);
  elements.panelColumn!.classList.toggle('collapsed', orbMode);
  elements.panelColumn!.classList.toggle('panel-open', !orbMode);
  elements.inputBar!.classList.toggle('input-hidden', orbMode);
  syncWindowMode();
}

function render(): void {
  renderMode();
  renderViewButtons();
  renderAnalysis();
  renderContentPanel();
  renderSendButton();
  renderTranscript();
  renderScreenshots();
}

/* ═══════════════════════════════════════════════════════
   STATE MUTATIONS
   ═══════════════════════════════════════════════════════ */

function upsertScreenshot(entry: ScreenshotEntry): void {
  const requestId = entry.request_id;
  if (!requestId) {
    state.screenshotHistory.unshift(entry);
    state.screenshotHistory = state.screenshotHistory.slice(0, 5);
    return;
  }

  const index = state.screenshotHistory.findIndex((item) => item.request_id === requestId);
  if (index === -1) {
    state.screenshotHistory.unshift(entry);
  } else {
    state.screenshotHistory[index] = entry;
    if (index !== 0) {
      state.screenshotHistory.unshift(state.screenshotHistory.splice(index, 1)[0]);
    }
  }
  state.screenshotHistory = state.screenshotHistory.slice(0, 5);
}

function appendTranscript(role: string, text: string): void {
  const cleaned = text.trim();
  if (!cleaned) {
    return;
  }
  state.transcriptEntries.push({ role, text: cleaned });
  state.transcriptEntries = state.transcriptEntries.slice(-100);
}

function applySnapshot(snapshot: {
  session_id?: string;
  status_message?: string;
  permission_warning?: string;
  confirmation_message?: string;
  analysis?: AnalysisResult | null;
  demo_mode?: boolean;
}): void {
  state.sessionId = snapshot.session_id || '';
  state.statusMessage = snapshot.status_message || 'Ready';
  state.permissionWarning = snapshot.permission_warning || '';
  state.confirmationMessage = snapshot.confirmation_message || '';
  state.analysis = snapshot.analysis || null;
  state.demoMode = Boolean(snapshot.demo_mode);
  state.aiRevealed = false;
}

function applyLiveSnapshot(snapshot: {
  live?: {
    connected?: boolean;
    message?: string;
    phase?: string;
    mic_active?: boolean;
  };
  transcript_entries?: TranscriptEntry[];
  screenshot_history?: ScreenshotEntry[];
  session_id?: string;
}): void {
  state.live.connected = Boolean(snapshot.live?.connected);
  state.live.message = snapshot.live?.message || state.live.message;
  state.live.phase = snapshot.live?.phase || '';
  state.live.micActive = Boolean(snapshot.live?.mic_active);
  state.transcriptEntries = snapshot.transcript_entries || [];
  state.screenshotHistory = snapshot.screenshot_history || [];
  if (snapshot.session_id) {
    state.sessionId = snapshot.session_id;
  }
}

function applyEvent(event: AppEvent): void {
  switch (event.type) {
    case 'status':
      state.statusMessage = event.message || '';
      state.captureInFlight = event.message === 'Capturing...' || event.message === 'Analyzing...';
      if (event.message === 'Capturing...') {
        state.analysis = null;
        state.aiRevealed = false;
        state.flagMode = false;
      }
      break;
    case 'permission.warning':
      state.permissionWarning = event.message || '';
      break;
    case 'analysis':
      state.analysis = {
        finding: event.finding || '',
        confidence: event.confidence || '',
        image_hash: event.image_hash || '',
        recommendation: event.recommendation || '',
        specialist_flags: event.specialist_flags || []
      };
      state.statusMessage = 'Analysis ready';
      state.captureInFlight = false;
      state.aiRevealed = false;
      state.flagMode = false;
      state.activeView = 'Insights';
      state.uiMode = 'bar';
      break;
    case 'confirmation':
      state.confirmationMessage = event.message || '';
      state.statusMessage = event.message || '';
      state.captureInFlight = false;
      state.flagMode = false;
      window.setTimeout(() => {
        collapseOverlay();
      }, 1600);
      break;
    case 'live.connection':
      state.live.connected = Boolean(event.connected);
      state.live.message = event.message || '';
      if (!event.connected) {
        state.live.phase = '';
        state.live.micActive = false;
      }
      if (liveMedia) {
        void liveMedia.handleLiveEvent(event);
      }
      break;
    case 'live.phase':
      state.live.phase = event.phase || '';
      break;
    case 'live.mic':
      state.live.micActive = Boolean(event.active);
      break;
    case 'live.message':
      appendTranscript(event.role || '', event.text || '');
      break;
    case 'live.user_transcript':
      if (event.is_final) {
        appendTranscript('user', event.text || '');
      }
      break;
    case 'live.screenshot':
      upsertScreenshot(event.event || {});
      if (event.event && event.event.image_b64) {
        state.activeView = 'QA';
        state.uiMode = 'bar';
      }
      break;
    case 'live.audio':
    case 'live.audio_clear':
      if (liveMedia) {
        void liveMedia.handleLiveEvent(event);
      }
      break;
    default:
      break;
  }

  render();
}

/* ═══════════════════════════════════════════════════════
   ACTIONS
   ═══════════════════════════════════════════════════════ */

function handleSimulate(): void {
  state.captureInFlight = true;
  state.statusMessage = 'Simulating...';
  state.analysis = null;
  state.aiRevealed = false;
  state.flagMode = false;
  state.bannerVisible = false;
  state.uiMode = 'bar';
  render();

  setTimeout(() => {
    applyEvent({
      type: 'analysis',
      finding: 'Right upper lobe nodule, 23mm. Suspicious morphology with spiculated margins. Comparison with prior CT from 6 months ago shows interval growth of 4mm.',
      confidence: 'high',
      image_hash: 'demo_sim_' + Date.now().toString(36),
      recommendation: 'CT-guided biopsy recommended. Pulmonology referral for bronchoscopy evaluation. Follow-up imaging in 3 months if biopsy deferred.',
      specialist_flags: ['Pulmonology', 'Oncology', 'Thoracic Surgery']
    });
  }, 800);
}

async function handleCapture(): Promise<void> {
  state.captureInFlight = true;
  state.statusMessage = 'Capturing...';
  state.confirmationMessage = '';
  state.analysis = null;
  state.aiRevealed = false;
  state.flagMode = false;
  state.bannerVisible = false;
  state.uiMode = 'bar';
  render();

  try {
    await window.copilotDesktop.showWindow();
    await window.copilotDesktop.capture();
  } catch (error) {
    const err = error as Error;
    state.captureInFlight = false;
    state.statusMessage = err.message;
    render();
  }
}

async function handleDismissAndHide(): Promise<void> {
  if (state.analysis && state.aiRevealed) {
    try {
      await window.copilotDesktop.dismiss();
    } catch (error) {
      const err = error as Error;
      state.statusMessage = err.message;
      render();
      return;
    }
  }

  collapseOverlay();
}

async function handleSend(): Promise<void> {
  const input = elements.askInput!;
  const text = input.value.trim();
  if (!text) return;

  if (state.inputMode === 'transcript') {
    try {
      await window.copilotDesktop.sendLiveText(text);
      input.value = '';
      state.activeView = 'Transcript';
      render();
    } catch (error) {
      const err = error as Error;
      appendTranscript('system', err.message);
      render();
    }
  } else {
    // Notes mode — treat as doctor read input
    state.doctorDraft = text;
    input.value = '';
    render();
  }
}

function connectEvents(): void {
  const socket = new WebSocket(window.copilotDesktop.eventsUrl);
  socket.addEventListener('message', (event) => {
    applyEvent(JSON.parse(event.data as string) as AppEvent);
  });
  socket.addEventListener('close', () => {
    window.setTimeout(connectEvents, 1000);
  });
}

/* ═══════════════════════════════════════════════════════
   ORB — Ring + mode toggle
   ═══════════════════════════════════════════════════════ */

function setupOrb(): void {
  const container = $('orb-container')!;
  const orb = $('orb')!;

  // Hover → show satellite ring
  container.addEventListener('mouseenter', () => {
    if (ringLeaveTimer) clearTimeout(ringLeaveTimer);
    container.classList.add('ring-open');
  });

  container.addEventListener('mouseleave', () => {
    ringLeaveTimer = setTimeout(() => {
      container.classList.remove('ring-open');
    }, 200);
  });

  // Click orb → expand to bar mode
  orb.addEventListener('click', () => {
    state.uiMode = 'bar';
    render();
  });

  // Satellite clicks → switch view + expand
  document.querySelectorAll<HTMLElement>('.satellite').forEach((sat) => {
    sat.addEventListener('click', () => {
      state.activeView = sat.dataset.view || state.activeView;
      state.uiMode = 'bar';
      render();
    });
  });
}

/* ═══════════════════════════════════════════════════════
   EVENT BINDING
   ═══════════════════════════════════════════════════════ */

function bindEvents(): void {
  // Nav pills
  document.querySelectorAll<HTMLElement>('.pill[data-view]').forEach((button) => {
    button.addEventListener('click', () => {
      state.activeView = button.dataset.view || state.activeView;
      render();
    });
  });

  // Mini-orb → collapse to orb mode
  elements.miniOrb!.addEventListener('click', () => {
    state.activeView = 'Insights';
    collapseOverlay();
  });

  // Doctor input
  elements.doctorInput!.addEventListener('input', (event) => {
    state.doctorDraft = (event.target as HTMLTextAreaElement).value;
    render();
  });

  // Flag input
  elements.flagInput!.addEventListener('input', (event) => {
    state.flagDraft = (event.target as HTMLInputElement).value;
  });

  // Reveal AI
  elements.revealButton!.addEventListener('click', () => {
    if (!state.doctorDraft.trim()) {
      state.statusMessage = 'Write your read before revealing the AI analysis.';
      render();
      return;
    }
    state.aiRevealed = true;
    state.flagMode = false;
    state.bannerVisible = false;
    render();
  });

  // Capture
  elements.captureButton!.addEventListener('click', handleCapture);

  // Agree / Dismiss
  elements.agreeButton!.addEventListener('click', handleDismissAndHide);

  // Disagree
  elements.disagreeButton!.addEventListener('click', () => {
    state.flagMode = !state.flagMode;
    render();
  });

  // Submit flag
  elements.submitFlagButton!.addEventListener('click', async () => {
    const overrideNote = state.flagDraft.trim() || state.doctorDraft.trim();
    try {
      await window.copilotDesktop.flag(overrideNote);
    } catch (error) {
      const err = error as Error;
      state.statusMessage = err.message;
      render();
    }
  });

  // Ask input — send
  elements.sendButton!.addEventListener('click', handleSend);

  elements.askInput!.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      void handleSend();
    }
  });

  // Input mode toggles (Notes / Transcription)
  document.querySelectorAll<HTMLElement>('.toggle-pill').forEach((pill) => {
    pill.addEventListener('click', () => {
      state.inputMode = (pill.dataset.mode as 'notes' | 'transcript') || state.inputMode;
      document.querySelectorAll<HTMLElement>('.toggle-pill').forEach((p) => {
        p.classList.toggle('active', p.dataset.mode === state.inputMode);
      });
      elements.askInput!.placeholder = state.inputMode === 'transcript'
        ? 'Ask what changed on screen or request a screenshot...'
        : 'Ask what you have in mind...';
    });
  });

  // Mic button
  elements.micButton!.addEventListener('click', async () => {
    try {
      if (state.live.micActive) {
        await window.copilotDesktop.stopMic();
      } else {
        await window.copilotDesktop.startMic();
      }
    } catch (error) {
      const err = error as Error;
      state.statusMessage = err.message;
      render();
    }
  });

  // Ask button → focus input
  elements.askButton!.addEventListener('click', () => {
    state.uiMode = 'bar';
    render();
    window.requestAnimationFrame(() => {
      elements.askInput!.focus();
    });
  });

  // Simulate button
  elements.simulateButton!.addEventListener('click', handleSimulate);

  // Send button visibility on input change
  elements.askInput!.addEventListener('input', () => {
    renderSendButton();
  });

  // Desktop errors
  window.copilotDesktop.onDesktopError((message) => {
    appendTranscript('system', message);
    state.statusMessage = message;
    render();
  });

  window.copilotDesktop.onWindowModeChange((payload) => {
    const nextMode: 'orb' | 'bar' = payload && payload.mode === 'bar' ? 'bar' : 'orb';
    if (state.uiMode !== nextMode) {
      state.uiMode = nextMode;
      render();
    }
  });

  // Live events
  window.copilotDesktop.onLiveEvent((liveEvent) => {
    applyEvent(liveEvent);
  });

  // Live commands
  window.copilotDesktop.onLiveCommand((command) => {
    if (!liveMedia) {
      window.copilotDesktop.respondLiveCommand(command.requestId, null, {
        code: 'renderer_unavailable',
        message: 'Live media controller is not initialized.'
      });
      return;
    }
    void liveMedia.handleCommand(command);
  });

  // Orb interactions
  setupOrb();
}

/* ═══════════════════════════════════════════════════════
   BOOTSTRAP
   ═══════════════════════════════════════════════════════ */

async function bootstrap(): Promise<void> {
  Object.assign(elements, {
    overlayRoot: $('overlay-root'),
    heroTitle: $('hero-title'),
    heroBody: $('hero-body'),
    statusBanner: $('status-banner'),
    liveBanner: $('live-banner'),
    warningBanner: $('warning-banner'),
    confidenceBadge: $('confidence-badge'),
    imageHash: $('image-hash'),
    doctorInput: $('doctor-input'),
    revealButton: $('reveal-button'),
    captureButton: $('capture-button'),
    analysisCard: $('analysis-card'),
    analysisState: $('analysis-state'),
    analysisText: $('analysis-text'),
    recommendationText: $('recommendation-text'),
    specialistFlags: $('specialist-flags'),
    agreeButton: $('agree-button'),
    disagreeButton: $('disagree-button'),
    flagForm: $('flag-form'),
    flagInput: $('flag-input'),
    submitFlagButton: $('submit-flag-button'),
    measureSummary: $('measure-summary'),
    compareDoctor: $('compare-doctor'),
    compareAi: $('compare-ai'),
    qaMeta: $('qa-meta'),
    qaImage: $('qa-image'),
    qaEmpty: $('qa-empty'),
    qaHistory: $('qa-history'),
    transcriptLog: $('transcript-log'),
    askInput: $('ask-input'),
    inputBar: $('input-bar'),
    sendButton: $('send-button'),
    micButton: $('mic-button'),
    miniOrb: $('mini-orb'),
    askButton: $('ask-button'),
    listeningIndicator: $('listening-indicator'),
    simulateButton: $('simulate-button'),
    contentPanel: $('content-panel'),
    panelColumn: $('panel-column')
  });

  const config = await window.copilotDesktop.getConfig();
  state.hotkey = config.hotkey.replace('CommandOrControl', 'Cmd');
  state.demoMode = Boolean(config.demoMode);

  liveMedia = new window.LiveMediaController({
    desktop: window.copilotDesktop,
    previewFps: config.livePreviewFps,
    previewMaxWidth: config.livePreviewMaxWidth,
    previewJpegQuality: config.livePreviewJpegQuality,
    micSampleRate: config.liveMicSampleRate,
    screenshotJpegQuality: config.screenshotJpegQuality / 100
  });

  bindEvents();
  render();

  try {
    const snapshot = await window.copilotDesktop.getState();
    applySnapshot(snapshot);
  } catch (error) {
    const err = error as Error;
    state.statusMessage = `Bridge unavailable: ${err.message}`;
    state.permissionWarning = '';
  }

  try {
    const liveSnapshot = await window.copilotDesktop.getLiveState();
    applyLiveSnapshot(liveSnapshot);
  } catch (error) {
    const err = error as Error;
    appendTranscript('system', `Live state unavailable: ${err.message}`);
  }

  try {
    connectEvents();
  } catch (error) {
    const err = error as Error;
    appendTranscript('system', `Event stream unavailable: ${err.message}`);
  }

  try {
    await liveMedia!.bootstrap();
    if (state.live.connected) {
      await liveMedia!.handleLiveEvent({
        type: 'live.connection',
        connected: true,
        message: state.live.message
      });
    }
  } catch (error) {
    const err = error as Error;
    appendTranscript('system', `Live bootstrap failed: ${err.message}`);
  }

  window.copilotDesktop.setIgnoreMouse(false);
  render();
}

void bootstrap();
