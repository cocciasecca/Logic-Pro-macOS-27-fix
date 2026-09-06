#!/bin/zsh
# Standalone read-only reference collector. No sudo, extraction or Logic launch.
set -eu
setopt PIPE_FAIL
out_dir="${1:-${0:A:h}}"
[[ -d "$out_dir" ]] || { print -u2 'Cartella di destinazione inesistente'; exit 1; }
report="$(mktemp "$out_dir/BNNS-reference.XXXXXX")"
stage="$(mktemp -d "${TMPDIR:-/tmp}/bnns-reference.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
{
  print 'BNNS reference report — v1'
  /usr/bin/sw_vers
  print "Process architecture: $(/usr/bin/uname -m)"
  print "Running under Rosetta: $(/usr/sbin/sysctl -in sysctl.proc_translated 2>/dev/null || print 0)"
  info='/Applications/Logic Pro.app/Contents/Info.plist'
  if [[ -f "$info" ]]; then
    print -n 'Logic version: '
    /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$info" || true
    print -n 'Logic build: '
    /usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$info" || true
  else
    print 'Logic not found at standard installation path (not required for symbol probe).'
  fi
} > "$report"

if ! /usr/bin/xcode-select -p >/dev/null 2>&1 || ! /usr/bin/xcrun --find clang >/dev/null 2>&1; then
  print 'Symbol probe not run: Apple Command Line Tools unavailable.' >> "$report"
  print "Report parziale creato: $report"
  print 'Invia questo file. Non occorre installare nulla per ora.'
  exit 0
fi
cat > "$stage/probe.c" <<'C'
#include <dlfcn.h>
#include <stdio.h>
int main(void) {
    const char *names[] = {
        "BNNSGraphCompileFromFile", "BNNSGraphExecute",
        "BNNSGraphOptionsCreateDefault", "BNNSGraphOptionsSetSingleThread",
        "BNNSGraphGetWorkspaceSize", "BNNSGraphGetSize",
        "BNNSGraphContextGetArgPosition", "BNNSGraphGetNumInputs",
        "BNNSGraphGetInputNames", "BNNSGraphGetNumOutputs",
        "BNNSGraphGetOutputNames", "BNNSGraphGetTensorDescriptor",
        "BNNSGraphOptionsSetPredefinedOptimizations", "BNNSGraphGetArgumentPosition"
    };
    void *lib = dlopen("/System/Library/Frameworks/Accelerate.framework/Accelerate", RTLD_LAZY | RTLD_LOCAL);
    if (!lib) { puts("ERROR: cannot load Accelerate"); return 1; }
    unsigned missing = 0;
    for (unsigned i = 0; i < sizeof(names)/sizeof(names[0]); ++i) {
        void *symbol = dlsym(lib, names[i]);
        Dl_info owner = {0};
        printf("%s: %s\n", names[i], symbol ? "PRESENT" : "MISSING");
        if (!symbol) ++missing;
        if (symbol && dladdr(symbol, &owner) && owner.dli_fname)
            printf("  implementation: %s\n", owner.dli_fname);
    }
    printf("Missing legacy symbols: %u/14\n", missing);
    puts("Presence only: ABI and Logic functionality not tested. No BNNS function invoked.");
    dlclose(lib);
    return 0;
}
C
if /usr/bin/xcrun clang -arch arm64 -Wall -Wextra -Werror "$stage/probe.c" -o "$stage/probe" 2> "$stage/compiler.log"; then
  if ! "$stage/probe" >> "$report" 2>&1; then
    print 'Symbol probe failed.' >> "$report"
  fi
else
  print 'Symbol probe not run: compilation failed.' >> "$report"
  print 'Compilazione non riuscita; il report contiene comunque versione e build.'
fi
print "Report creato: $report"
print 'Invia il file di testo. Non sono stati raccolti seriali, progetti, licenze o file personali.'
