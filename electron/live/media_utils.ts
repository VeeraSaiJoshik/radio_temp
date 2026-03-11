// Dual-environment module: works in Node.js (main/service) and in the browser renderer.
// In the browser, it is loaded as a plain <script> and exposes window.LiveMediaUtils.
// In Node.js, it is required as a CommonJS module.

type ByteLike =
  | Uint8Array
  | ArrayBuffer
  | ArrayBufferView
  | number[]
  | null
  | undefined;

function normalizeBytes(value: ByteLike): Uint8Array {
  if (value instanceof Uint8Array) {
    return value;
  }
  if (value instanceof ArrayBuffer) {
    return new Uint8Array(value);
  }
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(
      (value as ArrayBufferView).buffer,
      (value as ArrayBufferView).byteOffset,
      (value as ArrayBufferView).byteLength
    );
  }
  return new Uint8Array((value as number[]) || []);
}

function bytesToBase64(value: ByteLike): string {
  const bytes = normalizeBytes(value);
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(bytes).toString('base64');
  }

  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const slice = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...(slice as unknown as number[]));
  }
  return btoa(binary);
}

function base64ToBytes(base64: string): Uint8Array {
  if (!base64) {
    return new Uint8Array();
  }
  if (typeof Buffer !== 'undefined') {
    return new Uint8Array(Buffer.from(base64, 'base64'));
  }

  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

async function hashBytes(value: ByteLike): Promise<string> {
  const bytes = normalizeBytes(value);
  if (typeof require === 'function') {
    try {
      const { createHash } = require('crypto') as typeof import('crypto');
      return createHash('sha256')
        .update(Buffer.from(bytes))
        .digest('hex')
        .slice(0, 16);
    } catch (error) {
      // Fall back to Web Crypto when running in a browser-like runtime.
    }
  }

  const digest = await crypto.subtle.digest('SHA-256', bytes.buffer as ArrayBuffer);
  const digestBytes = new Uint8Array(digest);
  let output = '';
  for (let index = 0; index < 8; index += 1) {
    output += digestBytes[index].toString(16).padStart(2, '0');
  }
  return output;
}

function floatToInt16(sample: number): number {
  const clamped = Math.max(-1, Math.min(1, sample));
  return clamped < 0 ? Math.round(clamped * 0x8000) : Math.round(clamped * 0x7fff);
}

function float32ToPcm16(input: Float32Array | number[]): Int16Array {
  const source = input instanceof Float32Array ? input : new Float32Array(input || []);
  const output = new Int16Array(source.length);
  for (let index = 0; index < source.length; index += 1) {
    output[index] = floatToInt16(source[index]);
  }
  return output;
}

function downsampleFloat32ToPcm16(
  input: Float32Array | number[],
  inputSampleRate: number,
  outputSampleRate: number
): Int16Array {
  const source = input instanceof Float32Array ? input : new Float32Array(input || []);
  if (!source.length) {
    return new Int16Array();
  }
  if (inputSampleRate <= 0 || outputSampleRate <= 0) {
    throw new Error('Sample rates must be positive');
  }

  if (inputSampleRate === outputSampleRate) {
    return float32ToPcm16(source);
  }

  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.max(1, Math.round(source.length / ratio));
  const output = new Int16Array(outputLength);

  let outputIndex = 0;
  let inputIndex = 0;
  while (outputIndex < outputLength) {
    const nextInputIndex = Math.min(
      source.length,
      Math.round((outputIndex + 1) * ratio)
    );
    let sum = 0;
    let count = 0;
    while (inputIndex < nextInputIndex) {
      sum += source[inputIndex];
      count += 1;
      inputIndex += 1;
    }

    const sample = count ? sum / count : source[Math.min(source.length - 1, inputIndex)];
    output[outputIndex] = floatToInt16(sample);
    outputIndex += 1;
  }

  return output;
}

function pcm16ToFloat32(value: ByteLike): Float32Array {
  const bytes = normalizeBytes(value);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const sampleCount = Math.floor(bytes.byteLength / 2);
  const output = new Float32Array(sampleCount);
  for (let index = 0; index < sampleCount; index += 1) {
    output[index] = view.getInt16(index * 2, true) / 0x8000;
  }
  return output;
}

function pcm16ToBytes(value: Int16Array | ByteLike): Uint8Array {
  if (value instanceof Int16Array) {
    return new Uint8Array(value.buffer.slice(0));
  }
  return normalizeBytes(value as ByteLike);
}

export interface LiveMediaUtilsApi {
  base64ToBytes: (base64: string) => Uint8Array;
  bytesToBase64: (value: ByteLike) => string;
  downsampleFloat32ToPcm16: (
    input: Float32Array | number[],
    inputSampleRate: number,
    outputSampleRate: number
  ) => Int16Array;
  float32ToPcm16: (input: Float32Array | number[]) => Int16Array;
  hashBytes: (value: ByteLike) => Promise<string>;
  normalizeBytes: (value: ByteLike) => Uint8Array;
  pcm16ToBytes: (value: Int16Array | ByteLike) => Uint8Array;
  pcm16ToFloat32: (value: ByteLike) => Float32Array;
}

const api: LiveMediaUtilsApi = {
  base64ToBytes,
  bytesToBase64,
  downsampleFloat32ToPcm16,
  float32ToPcm16,
  hashBytes,
  normalizeBytes,
  pcm16ToBytes,
  pcm16ToFloat32
};

// Expose on globalThis for browser renderer usage (window.LiveMediaUtils).
if (typeof globalThis !== 'undefined' && !(globalThis as Record<string, unknown>)['LiveMediaUtils']) {
  (globalThis as Record<string, unknown>)['LiveMediaUtils'] = api;
}

export { base64ToBytes, bytesToBase64, downsampleFloat32ToPcm16, float32ToPcm16, hashBytes, normalizeBytes, pcm16ToBytes, pcm16ToFloat32 };
export default api;
