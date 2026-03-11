import {
  ActivityHandling,
  Behavior,
  EndSensitivity,
  FunctionResponseScheduling,
  Modality,
  StartSensitivity,
  TurnCoverage
} from '@google/genai';

export const SYSTEM_PROMPT = `
You are the screen-aware assistant for ReVU, a radiology workflow automation tool.

Product context:
- ReVU is a software layer that sits on top of existing PACS systems and removes repetitive manual work from the radiologist workflow.
- The product is not replacing radiologists. It is designed to give them back substantial time on measurement, comparison, reporting, and QA busywork so they can focus on diagnosis.
- Core features:
  1. Measurement assist: the radiologist clicks once on a lesion, segmentation runs automatically, real-world millimeter measurements are derived from DICOM metadata, and the result is written back into PACS as native annotations via DICOM SR.
  2. Follow-up comparison engine: maintain a lesion database keyed by patient and anatomical location so returning patients surface prior measurements automatically and the current structure can be pre-measured for one-click confirmation.
  3. Auto-report drafting: pre-populate structured report templates based on what the AI sees so radiologists edit instead of dictating boilerplate from scratch.
  4. QA diff layer: independently review every study, compare against the radiologist's final report, flag disagreements, and escalate low-confidence mismatches to a second human.
- Target buyers are hospital radiology departments and imaging centers.
- Technical direction includes PACS API integrations, DICOM SR, MedSAM-style segmentation, and lesion tracking.

Behavior rules:
- You may receive a low-resolution live visual feed of the user's current screen, but only after the app successfully starts display capture.
- When preview frames are flowing, that is real visual context from the user's visible screen. Use it, but only for details that are actually visible.
- Until at least one preview frame or screenshot has been received in the current session, assume you cannot currently see the user's screen.
- When you notice something clinically relevant or potentially helpful on screen — a possible finding, an unusual measurement, a workflow inefficiency, or something that looks off — speak up briefly. Be a proactive second pair of eyes.
- Do not narrate every single frame or minor UI change. Focus on things that actually matter: clinical observations, potential findings, workflow suggestions, or things that seem wrong.
- If the visible screen materially changes (new study loaded, different view, report opened), call the \`take_screenshot\` tool so the local backend receives a full-resolution capture.
- If the user says "take ss", "take screenshot", or a clearly equivalent instruction, call \`take_screenshot\` immediately.
- If the user says "call hotkey", "press the shortcut", "open/show/run the app", "show the overlay", or asks for a fresh full analysis of the current screen, call \`call_hotkey\` immediately.
- If the user says "close", "hide", or "dismiss" the overlay/app, call \`close_overlay\` immediately.
- Prefer \`call_hotkey\` when the user wants the overlay/backend analysis refreshed; prefer \`take_screenshot\` when you just need a full-resolution still without changing overlay state.
- If the screen changed substantially and a fresh local analysis card would help more than a standalone screenshot, you may proactively call \`call_hotkey\`.
- If a preview frame is too small or blurry to answer reliably, prefer calling \`take_screenshot\` instead of guessing.
- Only describe details that are directly visible in the most recent preview frames from the current session. Do not infer hidden windows, prior screens, metadata, or off-screen content.
- If you do not currently have reliable visual context, say that plainly instead of guessing.
- Always respond when the user speaks to you. Answer questions about the visible patient context, the current workflow, report wording, priors, measurements, product strategy, or workflow automation ideas concisely and directly.
- After a screenshot succeeds, keep confirmations brief unless the user asked a broader question.
- Never claim to know hidden metadata that is not visible on screen or returned by tools.
- If you are uncertain, say what is unclear and what screenshot or context would resolve it.
`.trim();

export const BOOTSTRAP_PROMPT = (
  "You may receive live preview frames from the user's screen during this session. " +
  "Until a preview frame arrives, assume you cannot currently see the screen. " +
  "Stay quiet unless the user asks a question or a meaningful screen change warrants `take_screenshot`. " +
  "Call `take_screenshot` immediately when the user says take ss. " +
  "Call `call_hotkey` immediately when the user asks you to press the shortcut, open/show/run the app or overlay, or rerun the full analysis. " +
  "Call `close_overlay` immediately when the user asks you to close, hide, or dismiss the overlay or app. " +
  "Do not respond to this message. Stay silent until the user speaks."
);

export interface FunctionDeclarationSchema {
  name: string;
  description: string;
  parameters: {
    type: string;
    properties: Record<string, { type: string }>;
    required: string[];
  };
}

export const TAKE_SCREENSHOT_DECLARATION: FunctionDeclarationSchema = {
  name: 'take_screenshot',
  description:
    'Capture a full-resolution screenshot of the current user screen and send it to the local backend. Returns only delivery status and metadata, never image data.',
  parameters: {
    type: 'object',
    properties: {
      reason: { type: 'string' }
    },
    required: ['reason']
  }
};

export const CALL_HOTKEY_DECLARATION: FunctionDeclarationSchema = {
  name: 'call_hotkey',
  description:
    'Trigger the copilot hotkey action: show the overlay window and run a fresh full screen capture plus AI analysis. Use this when the user asks to open/show/run the app or overlay, press the shortcut, or rerun analysis.',
  parameters: {
    type: 'object',
    properties: {
      reason: { type: 'string' }
    },
    required: ['reason']
  }
};

export const CLOSE_OVERLAY_DECLARATION: FunctionDeclarationSchema = {
  name: 'close_overlay',
  description:
    'Hide the copilot overlay window without taking a new screenshot. Use this when the user asks to close, hide, or dismiss the overlay or app.',
  parameters: {
    type: 'object',
    properties: {
      reason: { type: 'string' }
    },
    required: ['reason']
  }
};

export const MAX_RECONNECTS = 50;
export const RECONNECT_DELAY_MS = 1500;
export const COMMAND_TIMEOUT_MS = 15000;

export interface LiveRuntimeConfig {
  enabled: boolean;
  apiKey: string;
  initialMessage: string;
  model: string;
  screenshotWsUrl: string;
  screenshotAckTimeoutMs: number;
  screenshotRetryDelayMs: number;
  previewFps: number;
  previewMaxWidth: number;
  previewJpegQuality: number;
  voiceName: string;
  micMode: string;
  micSampleRate: number;
  micChunkMs: number;
  contextTriggerTokens: number;
  contextTargetTokens: number;
  systemPrompt: string;
  bootstrapPrompt: string;
  functionResponseScheduling: FunctionResponseScheduling;
  transparentSessionResumption: boolean;
}

function readInt(name: string, fallback: number): number {
  const value = Number.parseInt(process.env[name] || '', 10);
  return Number.isFinite(value) ? value : fallback;
}

function readFloat(name: string, fallback: number): number {
  const value = Number.parseFloat(process.env[name] || '');
  return Number.isFinite(value) ? value : fallback;
}

export function composeSystemInstruction(runtimeConfig: Pick<LiveRuntimeConfig, 'systemPrompt' | 'bootstrapPrompt'>): string {
  if (!runtimeConfig.bootstrapPrompt) {
    return runtimeConfig.systemPrompt;
  }
  return `${runtimeConfig.systemPrompt}\n\nSession bootstrap:\n${runtimeConfig.bootstrapPrompt}`;
}

export function buildRealtimeInputConfig(runtimeConfig: Pick<LiveRuntimeConfig, 'micMode'>): object {
  const continuous = (runtimeConfig.micMode || '').trim().toLowerCase() === 'continuous';
  if (continuous) {
    return {
      automaticActivityDetection: {
        disabled: false,
        startOfSpeechSensitivity: StartSensitivity.START_SENSITIVITY_HIGH,
        endOfSpeechSensitivity: EndSensitivity.END_SENSITIVITY_LOW,
        prefixPaddingMs: 100,
        silenceDurationMs: 700
      },
      activityHandling: ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
      turnCoverage: TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY
    };
  }

  return {
    automaticActivityDetection: {
      disabled: true
    },
    activityHandling: ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
    turnCoverage: TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY
  };
}

export function buildLiveConnectConfig(
  runtimeConfig: LiveRuntimeConfig,
  sessionResumptionHandle = ''
): object {
  const sessionResumption: Record<string, unknown> = {};
  if (sessionResumptionHandle) {
    sessionResumption.handle = sessionResumptionHandle;
  }
  if (runtimeConfig.transparentSessionResumption) {
    sessionResumption.transparent = true;
  }

  return {
    responseModalities: [Modality.AUDIO],
    inputAudioTranscription: {},
    outputAudioTranscription: {},
    realtimeInputConfig: buildRealtimeInputConfig(runtimeConfig),
    speechConfig: {
      voiceConfig: {
        prebuiltVoiceConfig: {
          voiceName: runtimeConfig.voiceName
        }
      }
    },
    systemInstruction: composeSystemInstruction(runtimeConfig),
    tools: [
      {
        functionDeclarations: [
          {
            name: TAKE_SCREENSHOT_DECLARATION.name,
            description: TAKE_SCREENSHOT_DECLARATION.description,
            parametersJsonSchema: TAKE_SCREENSHOT_DECLARATION.parameters,
            behavior: Behavior.NON_BLOCKING
          },
          {
            name: CALL_HOTKEY_DECLARATION.name,
            description: CALL_HOTKEY_DECLARATION.description,
            parametersJsonSchema: CALL_HOTKEY_DECLARATION.parameters,
            behavior: Behavior.NON_BLOCKING
          },
          {
            name: CLOSE_OVERLAY_DECLARATION.name,
            description: CLOSE_OVERLAY_DECLARATION.description,
            parametersJsonSchema: CLOSE_OVERLAY_DECLARATION.parameters,
            behavior: Behavior.NON_BLOCKING
          }
        ]
      }
    ],
    contextWindowCompression: {
      triggerTokens: String(runtimeConfig.contextTriggerTokens),
      slidingWindow: {
        targetTokens: String(runtimeConfig.contextTargetTokens)
      }
    },
    sessionResumption
  };
}

export function getLiveRuntimeConfig(options: { demoMode?: boolean } = {}): LiveRuntimeConfig {
  const demoMode = Boolean(options.demoMode);
  const apiKey = process.env.GEMINI_API_KEY || '';

  let initialMessage = 'Gemini Live unavailable';
  if (demoMode) {
    initialMessage = 'Gemini Live disabled in demo mode';
  } else if (apiKey) {
    initialMessage = 'Gemini Live connecting...';
  } else {
    initialMessage = 'Gemini Live disabled (set GEMINI_API_KEY)';
  }

  return {
    enabled: Boolean(apiKey) && !demoMode,
    apiKey,
    initialMessage,
    model:
      process.env.GEMINI_LIVE_MODEL || 'gemini-2.5-flash-native-audio-preview-12-2025',
    screenshotWsUrl:
      process.env.LIVE_SCREEN_WS_URL || 'ws://127.0.0.1:8100/live/screenshot',
    screenshotAckTimeoutMs: Math.round(
      readFloat('LIVE_SCREEN_ACK_TIMEOUT_SECONDS', 5) * 1000
    ),
    screenshotRetryDelayMs: Math.round(
      readFloat('LIVE_SCREEN_WS_RETRY_SECONDS', 1.5) * 1000
    ),
    previewFps: readFloat('LIVE_PREVIEW_FPS', 2),
    previewMaxWidth: readInt('LIVE_PREVIEW_MAX_WIDTH', 960),
    previewJpegQuality: readInt('LIVE_PREVIEW_JPEG_QUALITY', 70),
    voiceName: process.env.LIVE_VOICE_NAME || 'Kore',
    micMode: process.env.LIVE_MIC_MODE || 'continuous',
    micSampleRate: readInt('LIVE_MIC_SAMPLE_RATE', 16000),
    micChunkMs: readInt('LIVE_MIC_CHUNK_MS', 20),
    contextTriggerTokens: readInt('LIVE_CONTEXT_TRIGGER_TOKENS', 24576),
    contextTargetTokens: readInt('LIVE_CONTEXT_TARGET_TOKENS', 16384),
    systemPrompt: SYSTEM_PROMPT,
    bootstrapPrompt: BOOTSTRAP_PROMPT,
    functionResponseScheduling: FunctionResponseScheduling.WHEN_IDLE,
    transparentSessionResumption: false
  };
}
