#!/usr/bin/env bash
# Builds a release APK into mobile/dist/ from a clean native project (Expo prebuild + Gradle).
#
#   cp .env.example .env       # set EXPO_PUBLIC_API_BASE_URL first
#   npm run build:apk
#
# Signing: the generated Gradle project signs release builds with the debug keystore, which is
# fine for sideloading/testing. Configure a real keystore before distributing through a store.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${EXPO_PUBLIC_API_BASE_URL:-}" ]]; then
  echo "error: EXPO_PUBLIC_API_BASE_URL is not set (copy .env.example to .env and edit it)" >&2
  exit 1
fi

if [[ -z "${ANDROID_HOME:-}" ]]; then
  for candidate in \
    "$HOME/Library/Android/sdk" \
    "$HOME/Android/Sdk" \
    "/opt/homebrew/share/android-commandlinetools" \
    "$LOCALAPPDATA/Android/Sdk" \
    "$HOME/AppData/Local/Android/Sdk" \
    "/mnt/c/Users/$USER/AppData/Local/Android/Sdk" \
    "/c/Users/$USER/AppData/Local/Android/Sdk" \
    "C:/Android/Sdk"; do
    if [[ -d "$candidate/platform-tools" || -d "$candidate/cmdline-tools" ]]; then
      export ANDROID_HOME="$candidate"
      break
    fi
  done
fi
if [[ -z "${ANDROID_HOME:-}" ]]; then
  echo "error: Android SDK not found; set ANDROID_HOME" >&2
  exit 1
fi
export ANDROID_SDK_ROOT="$ANDROID_HOME"

if ! java -version 2>&1 | grep -qE 'version "(17|2[0-9])'; then
  echo "error: JDK 17+ is required on PATH (or set JAVA_HOME)" >&2
  exit 1
fi

# Phones are ARM; add x86_64 (e.g. ANDROID_ABIS=arm64-v8a,armeabi-v7a,x86_64) for x86 emulators.
ANDROID_ABIS="${ANDROID_ABIS:-arm64-v8a,armeabi-v7a}"

echo "API base URL : $EXPO_PUBLIC_API_BASE_URL"
echo "ABIs         : $ANDROID_ABIS"
echo "Android SDK  : $ANDROID_HOME"

[[ -d node_modules ]] || npm ci

# Regenerate android/ from app.config.ts so native config always matches (it is gitignored).
CI=1 npx expo prebuild --platform android --clean --no-install

(cd android && ./gradlew --no-daemon assembleRelease -PreactNativeArchitectures="$ANDROID_ABIS")

VERSION="$(node -p "require('./package.json').version")"
mkdir -p dist
OUT="dist/citysense-${VERSION}.apk"
cp android/app/build/outputs/apk/release/app-release.apk "$OUT"
echo
echo "APK ready: $ROOT/$OUT ($(du -h "$OUT" | cut -f1))"
