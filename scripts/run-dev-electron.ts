#!/usr/bin/env node

import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawn, spawnSync } from 'child_process';

const repoRoot = path.resolve(__dirname, '../..');
const sourceBinary: string = require('electron') as string;
const sourceApp = path.resolve(sourceBinary, '..', '..', '..');
const sourceBinaryName = path.basename(sourceBinary);

const appName = process.env.RADCOPILOT_DEV_APP_NAME || 'ReVU';
const bundleId = process.env.RADCOPILOT_DEV_BUNDLE_ID || 'com.radiologycopilot.revu.dev';
const metadataRoot = path.join(repoRoot, '.electron-dev');
const installRoot =
  process.env.RADCOPILOT_DEV_APP_HOME || path.join(os.homedir(), 'Applications');
const targetApp = path.join(installRoot, `${appName}.app`);
const metadataPath = path.join(metadataRoot, 'metadata.json');
const prepareOnly =
  process.argv.includes('--prepare-only') || process.env.RADCOPILOT_PREPARE_ONLY === '1';

interface HelperConfig {
  sourceAppName: string;
  sourceExecutable: string;
  targetAppName: string;
  targetExecutable: string;
  bundleId: string;
}

const helperConfigs: HelperConfig[] = [
  {
    sourceAppName: 'Electron Helper.app',
    sourceExecutable: 'Electron Helper',
    targetAppName: `${appName} Helper.app`,
    targetExecutable: `${appName} Helper`,
    bundleId: `${bundleId}.helper`
  },
  {
    sourceAppName: 'Electron Helper (Renderer).app',
    sourceExecutable: 'Electron Helper (Renderer)',
    targetAppName: `${appName} Helper (Renderer).app`,
    targetExecutable: `${appName} Helper (Renderer)`,
    bundleId: `${bundleId}.helper.renderer`
  },
  {
    sourceAppName: 'Electron Helper (GPU).app',
    sourceExecutable: 'Electron Helper (GPU)',
    targetAppName: `${appName} Helper (GPU).app`,
    targetExecutable: `${appName} Helper (GPU)`,
    bundleId: `${bundleId}.helper.gpu`
  },
  {
    sourceAppName: 'Electron Helper (Plugin).app',
    sourceExecutable: 'Electron Helper (Plugin)',
    targetAppName: `${appName} Helper (Plugin).app`,
    targetExecutable: `${appName} Helper (Plugin)`,
    bundleId: `${bundleId}.helper.plugin`
  }
];

function runChecked(command: string, args: string[], options: Parameters<typeof spawnSync>[2] = {}): string {
  const result = spawnSync(command, args, {
    encoding: 'utf8' as const,
    stdio: 'pipe' as const,
    ...options
  });

  if (result.status !== 0) {
    const stderr = String(result.stderr || '').trim();
    const stdout = String(result.stdout || '').trim();
    const detail = stderr || stdout || `exit ${result.status}`;
    throw new Error(`${command} ${args.join(' ')} failed: ${detail}`);
  }

  return String(result.stdout || '');
}

function readJson(filePath: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    return null;
  }
}

function writeJson(filePath: string, value: unknown): void {
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2));
}

interface AppSignature {
  appName: string;
  bundleId: string;
  sourceApp: string;
  sourceBinaryName: string;
  sourceBinaryMtimeMs: number;
}

function getSignature(): AppSignature {
  const sourceStats = fs.statSync(sourceBinary);
  return {
    appName,
    bundleId,
    sourceApp,
    sourceBinaryName,
    sourceBinaryMtimeMs: sourceStats.mtimeMs
  };
}

function ensureFreshBundle(): AppSignature {
  fs.mkdirSync(metadataRoot, { recursive: true });
  fs.mkdirSync(installRoot, { recursive: true });

  const currentSignature = getSignature();
  const priorSignature = readJson(metadataPath);
  const needsCopy =
    !fs.existsSync(targetApp) ||
    JSON.stringify(priorSignature) !== JSON.stringify(currentSignature);

  if (needsCopy) {
    fs.rmSync(targetApp, { recursive: true, force: true });
    runChecked('ditto', [sourceApp, targetApp]);
  }

  return currentSignature;
}

function renameExecutable(): string {
  const contentsDir = path.join(targetApp, 'Contents', 'MacOS');
  const originalBinary = path.join(contentsDir, sourceBinaryName);
  const targetBinary = path.join(contentsDir, appName);

  if (!fs.existsSync(targetBinary)) {
    if (!fs.existsSync(originalBinary)) {
      throw new Error(`Electron binary not found in ${contentsDir}`);
    }
    fs.renameSync(originalBinary, targetBinary);
  }

  return targetBinary;
}

function renameHelperApps(): void {
  const frameworksDir = path.join(targetApp, 'Contents', 'Frameworks');

  helperConfigs.forEach((helper) => {
    const sourcePath = path.join(frameworksDir, helper.sourceAppName);
    const targetPath = path.join(frameworksDir, helper.targetAppName);

    if (!fs.existsSync(targetPath) && fs.existsSync(sourcePath)) {
      fs.renameSync(sourcePath, targetPath);
    }

    if (!fs.existsSync(targetPath)) {
      return;
    }

    const macosDir = path.join(targetPath, 'Contents', 'MacOS');
    const sourceExecutablePath = path.join(macosDir, helper.sourceExecutable);
    const targetExecutablePath = path.join(macosDir, helper.targetExecutable);

    if (!fs.existsSync(targetExecutablePath) && fs.existsSync(sourceExecutablePath)) {
      fs.renameSync(sourceExecutablePath, targetExecutablePath);
    }
  });
}

function patchInfoPlist(): void {
  const plistPath = path.join(targetApp, 'Contents', 'Info.plist');
  const replacements: [string, string][] = [
    ['CFBundleDisplayName', appName],
    ['CFBundleExecutable', appName],
    ['CFBundleIdentifier', bundleId],
    ['CFBundleName', appName],
    [
      'NSMicrophoneUsageDescription',
      'ReVU needs microphone access for Gemini Live voice capture.'
    ],
    [
      'NSCameraUsageDescription',
      'ReVU may use camera APIs exposed by Chromium media permissions.'
    ]
  ];

  replacements.forEach(([key, value]) => {
    runChecked('plutil', ['-replace', key, '-string', value, plistPath]);
  });
}

function patchHelperPlists(): void {
  const frameworksDir = path.join(targetApp, 'Contents', 'Frameworks');
  helperConfigs.forEach((helper) => {
    const helperPlist = path.join(frameworksDir, helper.targetAppName, 'Contents', 'Info.plist');
    if (!fs.existsSync(helperPlist)) {
      return;
    }

    const helperDisplayName = helper.targetAppName.replace(/\.app$/u, '');
    const replacements: [string, string][] = [
      ['CFBundleDisplayName', helperDisplayName],
      ['CFBundleExecutable', helper.targetExecutable],
      ['CFBundleName', helperDisplayName],
      ['CFBundleIdentifier', helper.bundleId],
      [
        'NSMicrophoneUsageDescription',
        'ReVU needs microphone access for Gemini Live voice capture.'
      ],
      [
        'NSCameraUsageDescription',
        'ReVU may use camera APIs exposed by Chromium media permissions.'
      ]
    ];

    replacements.forEach(([key, value]) => {
      runChecked('plutil', ['-replace', key, '-string', value, helperPlist]);
    });
  });
}

function codesignBundle(): void {
  const frameworksDir = path.join(targetApp, 'Contents', 'Frameworks');
  const frameworkEntries = fs
    .readdirSync(frameworksDir)
    .filter((entry) => entry.endsWith('.framework'))
    .sort();

  frameworkEntries.forEach((entry) => {
    runChecked('codesign', ['--force', '--sign', '-', path.join(frameworksDir, entry)]);
  });

  helperConfigs.forEach((helper) => {
    const helperPath = path.join(frameworksDir, helper.targetAppName);
    if (!fs.existsSync(helperPath)) {
      return;
    }
    runChecked('codesign', [
      '--force',
      '--sign',
      '-',
      '--identifier',
      helper.bundleId,
      helperPath
    ]);
  });

  runChecked('codesign', ['--force', '--sign', '-', '--identifier', bundleId, targetApp]);
}

function prepareBundle(): string {
  const signature = ensureFreshBundle();
  const targetBinary = renameExecutable();
  renameHelperApps();
  patchInfoPlist();
  patchHelperPlists();
  codesignBundle();
  writeJson(metadataPath, signature);
  return targetBinary;
}

function launchBundle(targetBinary: string): void {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;

  const launchViaOpen =
    process.platform === 'darwin' &&
    process.env.RADCOPILOT_LAUNCH_OPEN !== '0' &&
    process.env.NODE_ENV !== 'development';

  const child = launchViaOpen
    ? spawn('open', ['-n', '-W', '-a', targetApp, '--args', repoRoot], {
        cwd: repoRoot,
        env,
        stdio: 'inherit'
      })
    : spawn(targetBinary, [repoRoot], {
        cwd: repoRoot,
        env,
        stdio: 'inherit'
      });

  child.on('exit', (code: number | null, signal: NodeJS.Signals | null) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code === null ? 0 : code);
  });
}

function main(): void {
  const targetBinary = prepareBundle();
  if (prepareOnly) {
    process.stdout.write(`${targetBinary}\n`);
    return;
  }
  launchBundle(targetBinary);
}

main();
