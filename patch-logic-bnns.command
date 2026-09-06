#!/bin/zsh
set -eu
setopt PIPE_FAIL

script_dir="${0:A:h}"
target="${LOGIC_APP:-/Applications/Logic Pro.app}"
framework="Contents/Frameworks/MAMachineLearning.framework/Versions/A/MAMachineLearning"
framework_dir="Contents/Frameworks/MAMachineLearning.framework/Versions/A"
mode="${1:-}"

if [[ "$mode" == "--diagnose" ]]; then
  exec /usr/bin/python3 "$script_dir/tools/bnns_probe.py" --app "$target"
fi
if [[ -n "$mode" ]]; then
  print -u2 "Usage: ./patch-logic-bnns.command"
  print -u2 "Optional: ./patch-logic-bnns.command --diagnose"
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
backup="/Applications/Logic Pro.app.BNNS-backup-$stamp"
installing="/Applications/.Logic Pro.app.BNNS-installing-$stamp"
tmp_parent="$(mktemp -d /private/tmp/logic-bnns-patch.XXXXXX)"
candidate="$tmp_parent/Logic Pro.app"
restore_needed=0

cleanup() {
  rm -rf -- "$tmp_parent"
}

rollback() {
  result=$?
  cleanup
  if (( restore_needed )) && [[ ! -e "$target" && -d "$backup" ]]; then
    print -u2 "Patch failed; restoring backup."
    sudo mv "$backup" "$target"
  fi
  if [[ -d "$installing" ]]; then
    print -u2 "Partial install left at: $installing"
  fi
  exit "$result"
}

trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if pgrep -x "Logic Pro" >/dev/null; then
  print -u2 "Quit Logic Pro before patching."
  exit 1
fi
[[ -d "$target" && -f "$target/$framework" ]] || { print -u2 "Missing $target"; exit 1; }
[[ ! -e "$backup" && ! -e "$installing" ]] || { print -u2 "Temporary path already exists; retry later."; exit 1; }

shim="$tmp_parent/BNNSCompat.dylib"
smoke="$tmp_parent/legacy_bnns_smoke"
model="$target/Contents/Frameworks/MAMachineLearning.framework/Versions/A/Resources/FSQ_44_i2ib8ecc9q_0881.mlmodelc/model_512_transformed.mil"

print "Building BNNS compatibility shim..."
xcrun clang -dynamiclib -arch arm64 -arch x86_64 -Wall -Wextra -Werror \
  -framework Accelerate -Wl,-reexport_framework,Accelerate \
  "$script_dir/shim/bnns_compat.c" -o "$shim"

print "Running BNNS smoke test..."
xcrun clang -arch arm64 -Wall -Wextra -Werror \
  "$script_dir/tools/legacy_bnns_smoke.c" -o "$smoke"
"$smoke" "$shim" "$model"

print "Preparing patched app copy..."
ditto "$target" "$candidate"
/usr/bin/python3 "$script_dir/tools/compat_patch.py" "$target/$framework" "$tmp_parent/MAMachineLearning"
cp "$tmp_parent/MAMachineLearning" "$candidate/$framework"
cp "$shim" "$candidate/$framework_dir/BNNSCompat.dylib"
codesign --force --deep --sign - "$candidate"
codesign --verify --deep --strict "$candidate"

print "Copying patched app to /Applications staging..."
sudo ditto "$candidate" "$installing"
sudo codesign --verify --deep --strict "$installing"

print "Backing up original Logic Pro.app..."
sudo mv "$target" "$backup"
restore_needed=1

print "Installing patched Logic Pro.app..."
sudo mv "$installing" "$target"
sudo codesign --verify --deep --strict "$target"
restore_needed=0
trap - EXIT
cleanup

print "Done."
print "Patched app: $target"
print "Backup:      $backup"
