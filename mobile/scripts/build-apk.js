const fs = require('fs');
const path = require('path');
const { execSync, spawnSync } = require('child_process');

const rootDir = path.resolve(__dirname, '..');
process.chdir(rootDir);

// 1. Read .env if present
const envPath = path.join(rootDir, '.env');
if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, 'utf8');
  for (const line of envContent.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx !== -1) {
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, '');
      if (!process.env[key]) {
        process.env[key] = val;
      }
    }
  }
}

// 2. Validate EXPO_PUBLIC_API_BASE_URL
const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
if (!apiBaseUrl) {
  console.error('error: EXPO_PUBLIC_API_BASE_URL is not set (copy .env.example to .env and edit it)');
  process.exit(1);
}

// 3. Locate Android SDK
let androidHome = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
if (!androidHome) {
  const home = process.env.HOME || process.env.USERPROFILE || '';
  const localAppData = process.env.LOCALAPPDATA || (home ? path.join(home, 'AppData', 'Local') : '');
  const candidates = [
    localAppData ? path.join(localAppData, 'Android', 'Sdk') : '',
    home ? path.join(home, 'Library', 'Android', 'sdk') : '',
    home ? path.join(home, 'Android', 'Sdk') : '',
    'C:\\Android\\Sdk',
    '/opt/homebrew/share/android-commandlinetools',
  ].filter(Boolean);

  for (const cand of candidates) {
    if (fs.existsSync(path.join(cand, 'platform-tools')) || fs.existsSync(path.join(cand, 'cmdline-tools'))) {
      androidHome = cand;
      break;
    }
  }
}

if (!androidHome || !fs.existsSync(androidHome)) {
  console.error('\n================================================================');
  console.error('  ERROR: Android SDK not found on this machine');
  console.error('================================================================');
  console.error('To compile a standalone APK locally:');
  console.error('  1. Install Android Studio (or Android SDK Command-Line Tools).');
  console.error('  2. Set ANDROID_HOME to your SDK location (e.g. %LOCALAPPDATA%\\Android\\Sdk).');
  console.error('  3. In SDK Manager, install Android 14/15 (API 34/35) and Build-Tools.');
  console.error('\nAlternatively, build in the Expo cloud with zero local setup:');
  console.error('  npx eas build -p android --profile preview');
  console.error('================================================================\n');
  process.exit(1);
}

process.env.ANDROID_HOME = androidHome;
process.env.ANDROID_SDK_ROOT = androidHome;

// 4. Verify Java version
try {
  const javaCheck = spawnSync('java', ['-version'], { encoding: 'utf8' });
  const javaOut = (javaCheck.stderr || '') + (javaCheck.stdout || '');
  const match = javaOut.match(/version "(17|2[0-9])/);
  if (!match) {
    console.error('error: JDK 17+ is required on PATH (or set JAVA_HOME)');
    process.exit(1);
  }
} catch (e) {
  console.error('error: Java executable not found on PATH');
  process.exit(1);
}

const androidAbis = process.env.ANDROID_ABIS || 'arm64-v8a,armeabi-v7a';
console.log('API base URL :', apiBaseUrl);
console.log('ABIs         :', androidAbis);
console.log('Android SDK  :', androidHome);

// 5. Prebuild android native project
console.log('\n--> Running expo prebuild...');
execSync('npx expo prebuild --platform android --clean --no-install', {
  stdio: 'inherit',
  env: { ...process.env, CI: '1' }
});

// 6. Build release APK with Gradle
const isWin = process.platform === 'win32';
const gradlewCmd = isWin ? 'gradlew.bat' : './gradlew';
const androidDir = path.join(rootDir, 'android');

console.log('\n--> Building release APK with Gradle...');
execSync(`${gradlewCmd} --no-daemon assembleRelease -PreactNativeArchitectures="${androidAbis}"`, {
  cwd: androidDir,
  stdio: 'inherit',
  env: process.env
});

// 7. Copy output APK to dist/
const pkg = JSON.parse(fs.readFileSync(path.join(rootDir, 'package.json'), 'utf8'));
const version = pkg.version || '1.0.0';
const distDir = path.join(rootDir, 'dist');
if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

const builtApk = path.join(androidDir, 'app', 'build', 'outputs', 'apk', 'release', 'app-release.apk');
const outApk = path.join(distDir, `citysense-${version}.apk`);

if (fs.existsSync(builtApk)) {
  fs.copyFileSync(builtApk, outApk);
  const sizeMb = (fs.statSync(outApk).size / (1024 * 1024)).toFixed(1);
  console.log(`\nAPK ready: ${outApk} (${sizeMb} MB)`);
} else {
  console.error(`\nerror: Built APK not found at ${builtApk}`);
  process.exit(1);
}
