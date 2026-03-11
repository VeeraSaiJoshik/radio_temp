import test from 'node:test';
import assert from 'node:assert/strict';

import {
  BOOTSTRAP_PROMPT,
  SYSTEM_PROMPT,
  TAKE_SCREENSHOT_DECLARATION,
  buildLiveConnectConfig,
  LiveRuntimeConfig
} from './config';
import { FunctionResponseScheduling } from '@google/genai';

test('buildLiveConnectConfig preserves the current live session shape', () => {
  const runtimeConfig: LiveRuntimeConfig = {
    micMode: 'continuous',
    voiceName: 'Kore',
    systemPrompt: SYSTEM_PROMPT,
    bootstrapPrompt: BOOTSTRAP_PROMPT,
    contextTriggerTokens: 24576,
    contextTargetTokens: 16384,
    enabled: true,
    apiKey: 'test',
    initialMessage: 'connecting',
    model: 'test-model',
    screenshotWsUrl: 'ws://localhost',
    screenshotAckTimeoutMs: 5000,
    screenshotRetryDelayMs: 1500,
    previewFps: 2,
    previewMaxWidth: 960,
    previewJpegQuality: 70,
    micSampleRate: 16000,
    micChunkMs: 20,
    functionResponseScheduling: FunctionResponseScheduling.WHEN_IDLE,
    transparentSessionResumption: false
  };

  const config = buildLiveConnectConfig(runtimeConfig, 'resume-handle') as Record<string, unknown>;

  assert.deepEqual(config['responseModalities'], ['AUDIO']);
  assert.deepEqual(config['inputAudioTranscription'], {});
  assert.deepEqual(config['outputAudioTranscription'], {});
  const realtimeInputConfig = config['realtimeInputConfig'] as Record<string, unknown>;
  const aad = realtimeInputConfig['automaticActivityDetection'] as Record<string, unknown>;
  assert.equal(aad['disabled'], false);
  assert.equal(aad['startOfSpeechSensitivity'], 'START_SENSITIVITY_HIGH');
  assert.equal(aad['endOfSpeechSensitivity'], 'END_SENSITIVITY_LOW');
  const speechConfig = config['speechConfig'] as Record<string, unknown>;
  const voiceConfig = speechConfig['voiceConfig'] as Record<string, unknown>;
  const prebuiltVoiceConfig = voiceConfig['prebuiltVoiceConfig'] as Record<string, unknown>;
  assert.equal(prebuiltVoiceConfig['voiceName'], 'Kore');
  assert.match(config['systemInstruction'] as string, /Session bootstrap:/u);
  assert.match(
    config['systemInstruction'] as string,
    /Until at least one preview frame or screenshot has been received/u
  );
  assert.match(BOOTSTRAP_PROMPT, /Until a preview frame arrives/u);
  const tools = config['tools'] as Array<{ functionDeclarations: Array<{ name: string }> }>;
  assert.equal(tools[0].functionDeclarations[0].name, TAKE_SCREENSHOT_DECLARATION.name);
  const contextWindowCompression = config['contextWindowCompression'] as Record<string, unknown>;
  assert.equal(contextWindowCompression['triggerTokens'], '24576');
  const slidingWindow = contextWindowCompression['slidingWindow'] as Record<string, unknown>;
  assert.equal(slidingWindow['targetTokens'], '16384');
  const sessionResumption = config['sessionResumption'] as Record<string, unknown>;
  assert.equal(sessionResumption['handle'], 'resume-handle');
  assert.equal('transparent' in sessionResumption, false);
  assert.equal('explicitVadSignal' in config, false);
});
