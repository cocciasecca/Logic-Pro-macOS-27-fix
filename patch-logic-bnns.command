#!/bin/zsh
set -eu
setopt PIPE_FAIL

script_dir="${0:A:h}"
target="/Applications/Logic Pro.app"
framework="Contents/Frameworks/MAMachineLearning.framework/Versions/A/MAMachineLearning"
stamp="$(date +%Y%m%d-%H%M%S)"
backup="/Applications/Logic Pro.app.BNNS-backup-$stamp"
installing="/Applications/.Logic Pro.app.BNNS-installing-$stamp"
tmp_parent="$(mktemp -d /private/tmp/logic-bnns-install.XXXXXX)"
candidate="$tmp_parent/Logic Pro.app"
restore_needed=0

cleanup() {
  rm -rf -- "$tmp_parent"
}
rollback() {
  result=$?
  cleanup
  if (( restore_needed )) && [[ ! -e "$target" && -d "$backup" ]]; then
    print -u2 "Install failed; restoring backup to $target"
    sudo mv "$backup" "$target"
  fi
  if [[ -d "$installing" ]]; then
    print -u2 "Partial install was left at: $installing"
  fi
  exit "$result"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if pgrep -x "Logic Pro" >/dev/null; then
  print -u2 "Quit Logic Pro before installing."
  exit 1
fi
[[ -d "$target" && -f "$target/$framework" ]] || { print -u2 "Missing $target"; exit 1; }
[[ ! -e "$backup" && ! -e "$installing" ]] || { print -u2 "Backup/install path already exists; retry later."; exit 1; }

print "Preparing patched Logic copy in temporary storage..."
"$script_dir/patch-logic-bnns.command" --prepare "$candidate"

print "Copying candidate into /Applications staging area..."
sudo ditto "$candidate" "$installing"
sudo codesign --verify --deep --strict "$installing"

print "Backing up current Logic Pro.app to:"
print "$backup"
sudo mv "$target" "$backup"
restore_needed=1

print "Installing patched Logic Pro.app as the main app..."
sudo mv "$installing" "$target"
sudo codesign --verify --deep --strict "$target"
restore_needed=0
trap - EXIT
cleanup

print "Done."
print "Installed: $target"
print "Backup:    $backup"
print "If you need to restore manually:"
print "  sudo mv '$target' '/Applications/Logic Pro.app.BNNS-failed-$stamp'"
print "  sudo mv '$backup' '$target'"
