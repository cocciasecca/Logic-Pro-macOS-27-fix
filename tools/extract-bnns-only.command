#!/bin/zsh
# Selective reference extraction. Requires macOS 26 on Apple Silicon.
# CLI verified against https://blacktop.github.io/ipsw/docs/cli/ipsw/dyld/extract/
set -eu
setopt PIPE_FAIL
fail() { print -u2 "Errore: $1"; exit 1; }
[[ "$(/usr/bin/sw_vers -productVersion)" == 26.* ]] || fail 'Esegui sul Mac con macOS 26.'
[[ "$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null || true)" == 1 ]] || fail 'Serve un Mac Apple Silicon.'
cache='/System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/dyld_shared_cache_arm64e'
image='/System/Library/Frameworks/Accelerate.framework/Versions/A/Frameworks/vecLib.framework/Versions/A/libBNNS.dylib'
[[ -r "$cache" ]] || fail 'Cache di sistema non trovata o non leggibile.'
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v ipsw >/dev/null 2>&1; then
  command -v brew >/dev/null 2>&1 || fail 'Homebrew non trovato. Invia questo messaggio a chi ti ha passato lo script.'
  print 'Installazione di ipsw tramite Homebrew...'
  brew install ipsw
fi
out="$(mktemp -d "$HOME/Desktop/BNNS-only.XXXXXX")"
mkdir "$out/BNNS-reference"
print "Estrazione della sola libBNNS.dylib in: $out"
print 'La cache di sistema viene letta sul posto, non copiata né estratta per intero.'
trap 'print -u2 "Interrotto. File parziali conservati in: $out"; exit 130' INT
trap 'print -u2 "Interrotto. File parziali conservati in: $out"; exit 143' TERM
# Explicit --all=false prevents configuration defaults from selecting every image.
# No --stubs: avoids building an address-to-symbol cache for the entire system.
if ! ipsw dyld extract "$cache" "$image" --all=false --stubs=false --objc=false --slide \
  --output "$out/BNNS-reference" > "$out/extraction.log" 2>&1; then
  print -u2 "Estrazione fallita. Invia: $out/extraction.log"
  /usr/bin/tail -n 15 "$out/extraction.log"
  exit 1
fi
lib="$out/BNNS-reference/libBNNS.dylib"
[[ -s "$lib" ]] || fail "Libreria non prodotta. Invia $out/extraction.log"
/usr/bin/sw_vers > "$out/BNNS-reference/macos.txt"
ipsw version > "$out/BNNS-reference/extractor-version.txt" 2>&1 || true
/usr/bin/file "$lib" > "$out/BNNS-reference/file-info.txt"
/usr/bin/shasum -a 256 "$lib" | /usr/bin/awk '{print $1 "  libBNNS.dylib"}' > "$out/BNNS-reference/SHA256.txt"
if /usr/bin/xcrun --find otool >/dev/null 2>&1; then
  /usr/bin/xcrun otool -L "$lib" > "$out/BNNS-reference/dependencies.txt" 2>&1 || true
fi
print 'Selective ipsw extraction with --slide. For analysis; standalone loading is not verified.' > "$out/BNNS-reference/README.txt"
/usr/bin/ditto -c -k --keepParent "$out/BNNS-reference" "$out/BNNS-macOS26.zip"
print "Fatto! Invia: $out/BNNS-macOS26.zip"
/usr/bin/open -R "$out/BNNS-macOS26.zip"
