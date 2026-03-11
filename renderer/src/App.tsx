import { useEffect, useRef, useCallback } from 'react';
import { AppContext } from './hooks/useAppContext';
import { useAppState } from './hooks/useAppState';
import { TopBar } from './components/TopBar';
import { ContentPanel } from './components/ContentPanel';
import { InputBar } from './components/InputBar';
import type { LiveEvent, ILiveMediaController } from './types/electron';
import type { InputMode } from './store/appState';

export default function App() {
  const { state, actions } = useAppState();
  const liveMediaRef = useRef<ILiveMediaController | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  // ─── Event application ─────────────────────────────────────────────────────

  const applyLiveEvent = useCallback((event: LiveEvent) => {
    const raw = event as unknown as Record<string, unknown>;
    switch (event.type) {
      case 'status':
        actions.setStatus((event.message as string) || '');
        if (event.message === 'Capturing...' || event.message === 'Analyzing...') {
          actions.setCaptureInFlight(true);
        }
        if (event.message === 'Capturing...') {
          actions.setAnalysis(null);
          actions.setAiRevealed(false);
          actions.setFlagMode(false);
        }
        break;

      case 'permission.warning':
        actions.setPermissionWarning((event.message as string) || '');
        break;

      case 'analysis':
        actions.applyAnalysisEvent({
          finding: (raw.finding as string) || '',
          confidence: (raw.confidence as string) || 'low',
          image_hash: (raw.image_hash as string) || '',
          recommendation: raw.recommendation as string | undefined,
          specialist_flags: raw.specialist_flags as string[] | undefined,
        });
        actions.setCaptureInFlight(false);
        break;

      case 'confirmation':
        actions.setConfirmationMessage((event.message as string) || '');
        actions.setStatus((event.message as string) || '');
        actions.setCaptureInFlight(false);
        actions.setFlagMode(false);
        window.setTimeout(() => {
          window.copilotDesktop.hideWindow();
        }, 1600);
        break;

      case 'live.connection':
        actions.setLiveConnected(Boolean(event.connected), event.message || '');
        if (liveMediaRef.current) {
          void liveMediaRef.current.handleLiveEvent(event);
        }
        break;

      case 'live.phase':
        actions.setLivePhase(event.phase || '');
        if (event.phase === 'Waiting for input' || event.phase === 'Listening continuously') {
          actions.setAiSpeaking(false);
          actions.setAiThinking(false);
        }
        break;

      case 'live.mic':
        actions.setLiveMicActive(Boolean(event.active));
        break;

      case 'live.message':
        actions.appendTranscript(
          (event.role as 'user' | 'assistant' | 'system') || 'system',
          event.text || ''
        );
        break;

      case 'live.user_transcript':
        if (event.is_final) {
          actions.appendTranscript('user', event.text || '');
          actions.setAiThinking(true);
        }
        break;

      case 'live.screenshot':
        if (event.event) {
          actions.upsertScreenshot(event.event);
        }
        break;

      case 'live.audio':
        actions.setAiSpeaking(true);
        if (liveMediaRef.current) {
          void liveMediaRef.current.handleLiveEvent(event);
        }
        break;

      case 'live.audio_clear':
        actions.setAiSpeaking(false);
        if (liveMediaRef.current) {
          void liveMediaRef.current.handleLiveEvent(event);
        }
        break;

      default:
        break;
    }
  }, [actions]);

  // ─── WebSocket event stream ─────────────────────────────────────────────────

  const connectEvents = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.close();
    }
    if (!window.copilotDesktop) return;
    try {
      const socket = new WebSocket(window.copilotDesktop.eventsUrl);
      socketRef.current = socket;
      socket.addEventListener('message', (evt) => {
        try {
          applyLiveEvent(JSON.parse(evt.data as string) as LiveEvent);
        } catch {
          // Malformed event — ignore
        }
      });
      socket.addEventListener('close', () => {
        window.setTimeout(connectEvents, 1000);
      });
    } catch (error) {
      actions.appendTranscript('system', `Event stream unavailable: ${(error as Error).message}`);
    }
  }, [applyLiveEvent, actions]);

  // ─── Bootstrap ─────────────────────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      if (!window.copilotDesktop) {
        console.warn('copilotDesktop not available — running outside Electron?');
        return;
      }

      window.copilotDesktop.setIgnoreMouse(false);

      // Get config
      let config;
      try {
        config = await window.copilotDesktop.getConfig();
        if (cancelled) return;
        actions.setHotkey(config.hotkey.replace('CommandOrControl', 'Cmd'));
        actions.setDemoMode(Boolean(config.demoMode));
      } catch (err) {
        if (!cancelled) actions.appendTranscript('system', `Config unavailable: ${(err as Error).message}`);
        return;
      }

      // Initialize LiveMediaController (injected by legacy <script> tag in Electron)
      if (window.LiveMediaController) {
        liveMediaRef.current = new window.LiveMediaController({
          desktop: window.copilotDesktop,
          previewFps: config.livePreviewFps,
          previewMaxWidth: config.livePreviewMaxWidth,
          previewJpegQuality: config.livePreviewJpegQuality,
          micSampleRate: config.liveMicSampleRate,
          screenshotJpegQuality: config.screenshotJpegQuality / 100,
        });
      }

      // Register IPC callbacks
      window.copilotDesktop.onDesktopError((message) => {
        if (cancelled) return;
        actions.appendTranscript('system', message);
        actions.setStatus(message);
      });


      window.copilotDesktop.onWindowModeChange(({ mode }) => {
        if (cancelled) return;
        actions.setWindowMode(mode);
      });

      window.copilotDesktop.onLiveEvent((liveEvent) => {
        if (cancelled) return;
        applyLiveEvent(liveEvent);
      });

      window.copilotDesktop.onLiveCommand((command) => {
        if (cancelled) return;
        if (!liveMediaRef.current) {
          window.copilotDesktop.respondLiveCommand(command.requestId, null, {
            code: 'renderer_unavailable',
            message: 'Live media controller is not initialized.',
          });
          return;
        }
        void liveMediaRef.current.handleCommand(command);
      });

      // Initial state fetch
      try {
        const snapshot = await window.copilotDesktop.getState();
        if (!cancelled) actions.applySnapshot(snapshot);
      } catch (err) {
        if (!cancelled) actions.setStatus(`Bridge unavailable: ${(err as Error).message}`);
      }

      try {
        const liveSnapshot = await window.copilotDesktop.getLiveState();
        if (!cancelled) actions.applyLiveSnapshot(liveSnapshot);
      } catch (err) {
        if (!cancelled) actions.appendTranscript('system', `Live state unavailable: ${(err as Error).message}`);
      }

      // Connect WebSocket event stream
      if (!cancelled) connectEvents();

      // Bootstrap live media
      if (liveMediaRef.current && !cancelled) {
        try {
          await liveMediaRef.current.bootstrap();
          const currentLiveState = await window.copilotDesktop.getLiveState();
          if (!cancelled && currentLiveState.live?.connected) {
            await liveMediaRef.current.handleLiveEvent({
              type: 'live.connection',
              connected: true,
              message: currentLiveState.live.message,
            });
          }
        } catch (err) {
          if (!cancelled) actions.appendTranscript('system', `Live bootstrap failed: ${(err as Error).message}`);
        }
      }

    }

    void bootstrap();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Handlers ──────────────────────────────────────────────────────────────

  const handleCapture = useCallback(async () => {
    actions.setCaptureInFlight(true);
    actions.setStatus('Capturing...');
    actions.setConfirmationMessage('');
    actions.setAnalysis(null);
    actions.setAiRevealed(false);
    actions.setFlagMode(false);

    try {
      await window.copilotDesktop.showWindow();
      await window.copilotDesktop.capture();
    } catch (error: unknown) {
      actions.setCaptureInFlight(false);
      actions.setStatus((error as Error).message);
    }
  }, [actions]);

  const handleSimulate = useCallback(() => {
    actions.setCaptureInFlight(true);
    actions.setStatus('Simulating...');
    actions.setAnalysis(null);
    actions.setAiRevealed(false);
    actions.setFlagMode(false);

    setTimeout(() => {
      actions.applyAnalysisEvent({
        finding:
          'Right upper lobe nodule, 23mm. Suspicious morphology with spiculated margins. Comparison with prior CT from 6 months ago shows interval growth of 4mm.',
        confidence: 'high',
        image_hash: 'demo_sim_' + Date.now().toString(36),
        recommendation:
          'CT-guided biopsy recommended. Pulmonology referral for bronchoscopy evaluation. Follow-up imaging in 3 months if biopsy deferred.',
        specialist_flags: ['Pulmonology', 'Oncology', 'Thoracic Surgery'],
      });
    }, 800);
  }, [actions]);

  const handleMicClick = useCallback(async () => {
    try {
      if (state.live.micActive) {
        await window.copilotDesktop.stopMic();
      } else {
        await window.copilotDesktop.startMic();
      }
    } catch (error: unknown) {
      actions.setStatus((error as Error).message);
    }
  }, [state.live.micActive, actions]);

  const handleAskClick = useCallback(() => {
    const input = document.querySelector<HTMLInputElement>('#ask-text-input');
    if (input) input.focus();
  }, []);

  const handleSend = useCallback(async (text: string, mode: InputMode) => {
    if (mode === 'transcript') {
      try {
        await window.copilotDesktop.sendLiveText(text);
        actions.setActiveView('Transcript');
      } catch (error: unknown) {
        actions.appendTranscript('system', (error as Error).message);
      }
    } else {
      actions.setDoctorDraft(text);
    }
  }, [actions]);

  // ─── Render ────────────────────────────────────────────────────────────────

  if (state.windowMode === 'orb') {
    return (
      <AppContext.Provider value={{ state, actions }}>
        <main className="app-drag w-full h-full flex items-center justify-center">
          <div className="w-12 h-12 rounded-full bg-white/10 border border-white/20 backdrop-blur-sm shadow-lg" />
        </main>
      </AppContext.Provider>
    );
  }

  return (
    <AppContext.Provider value={{ state, actions }}>
      <main className="app-drag w-full h-full flex flex-col overflow-hidden p-0">
        {/* Panel column — the glass surface */}
        <div className={[
          'relative flex flex-col w-full flex-1 min-h-0 overflow-hidden',
          'rounded-[22px] border border-white/[0.14]',
          'bg-[rgba(10,14,22,0.46)]',
          'shadow-[0_24px_54px_rgba(0,0,0,0.28)]',
          'transition-[opacity,transform,box-shadow,border-color] duration-200 ease-out',
        ].join(' ')}>
          <TopBar
            onMicClick={handleMicClick}
            onAskClick={handleAskClick}
            onSimulateClick={handleSimulate}
          />
          <ContentPanel onCapture={handleCapture} />
          <InputBar onSend={handleSend} />
        </div>
      </main>
    </AppContext.Provider>
  );
}
