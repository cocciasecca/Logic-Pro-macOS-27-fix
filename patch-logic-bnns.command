#!/bin/zsh
set -eu
setopt PIPE_FAIL

APP="/Applications/Logic Pro.app"
BACKUP="/Applications/Logic Pro.app.bak"
FRAMEWORK_REL="Contents/Frameworks/MAMachineLearning.framework/Versions/A/MAMachineLearning"
SYMBOL="_BNNSGraphGetSize"
PATCHED_CREATED=0
BACKUP_MOVED=0
work_dir=""

bold() {
  printf '\033[1m%s\033[0m\n' "$1"
}

technical() {
  printf '%s\n' "$1"
}

die() {
  printf '\033[1mError\033[0m\n%s\n' "$1" >&2
  exit 1
}

rollback() {
  status=$?
  trap - EXIT INT TERM
  if [[ -n "$work_dir" && -d "$work_dir" ]]; then
    rm -rf -- "$work_dir"
  fi
  if (( status != 0 )) && (( BACKUP_MOVED == 1 )); then
    bold "Restoring the original Logic app"
    if [[ -e "$APP" ]]; then
      rm -rf -- "$APP"
    fi
    mv -- "$BACKUP" "$APP"
    technical "Rollback completed."
  fi
  exit "$status"
}

trap rollback EXIT INT TERM

if (( EUID != 0 )); then
  bold "Administrator permission is required"
  technical "Restarting this script with sudo."
  exec sudo -- "$0" "$@"
fi

[[ -d "$APP" ]] || die "Logic Pro was not found at $APP"
[[ ! -e "$BACKUP" ]] || die "$BACKUP already exists. Move or remove that backup before running this script again."
[[ -f "$APP/$FRAMEWORK_REL" ]] || die "MAMachineLearning.framework was not found in the Logic app."

work_dir="$(mktemp -d /private/tmp/logic-bnns-patch.XXXXXX)"

bold "Checking the Logic app"
technical "Application: $APP"
technical "Target symbol: $SYMBOL"

if xcrun dyld_info -imports "$APP/$FRAMEWORK_REL" 2>/dev/null | grep -F "$SYMBOL [weak-import]" >/dev/null; then
  die "This Logic installation already has the BNNS weak-import patch."
fi

bold "Backing up the original Logic app"
technical "Moving $APP to $BACKUP"
mv -- "$APP" "$BACKUP"
BACKUP_MOVED=1

bold "Creating the patched Logic app"
technical "Copying the backup to $APP"
ditto "$BACKUP" "$APP"
PATCHED_CREATED=1

cp -p "$APP/$FRAMEWORK_REL" "$work_dir/MAMachineLearning"

bold "Patching the Logic app file"
technical "Changing $SYMBOL from a strong import to a weak import."

/usr/bin/python3 - "$work_dir/MAMachineLearning" "$work_dir/MAMachineLearning.patched" "$SYMBOL" <<'PY'
import struct
import sys
from pathlib import Path

source, output, wanted = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
data = bytearray(source.read_bytes())
LC_SYMTAB = 0x2
LC_DYLD_CHAINED_FIXUPS = 0x80000034
N_WEAK_REF = 0x0040

def c_string(offset):
    end = data.index(0, offset)
    return bytes(data[offset:end]).decode("utf-8")

def macho_slices():
    magic = bytes(data[:4])
    if magic == b"\xca\xfe\xba\xbe":
        count = struct.unpack_from(">I", data, 4)[0]
        for index in range(count):
            cpu, subtype, offset, size, align = struct.unpack_from(">IIIII", data, 8 + index * 20)
            yield cpu, offset, size
    elif magic == b"\xcf\xfa\xed\xfe":
        yield struct.unpack_from("<I", data, 4)[0], 0, len(data)
    else:
        raise RuntimeError(f"unsupported Mach-O format: {magic.hex()}")

patched_slices = 0
for cpu, base, size in macho_slices():
    if struct.unpack_from("<I", data, base)[0] != 0xFEEDFACF:
        raise RuntimeError("only 64-bit little-endian Mach-O slices are supported")

    command_count = struct.unpack_from("<I", data, base + 16)[0]
    cursor = base + 32
    symtab = None
    fixups = None
    for _ in range(command_count):
        command, command_size = struct.unpack_from("<II", data, cursor)
        if command == LC_SYMTAB:
            symtab = struct.unpack_from("<IIII", data, cursor + 8)
        elif command == LC_DYLD_CHAINED_FIXUPS:
            fixups = struct.unpack_from("<II", data, cursor + 8)
        cursor += command_size

    if symtab is None or fixups is None:
        raise RuntimeError(f"required Mach-O data is missing in CPU slice 0x{cpu:x}")

    fixups_offset, fixups_size = fixups
    header = base + fixups_offset
    _, _, imports_offset, symbols_offset, imports_count, imports_format, _ = struct.unpack_from(
        "<7I", data, header
    )
    entry_sizes = {1: 4, 2: 8, 3: 16}
    if imports_format not in entry_sizes:
        raise RuntimeError(f"unsupported chained-import format {imports_format}")

    import_matches = 0
    for index in range(imports_count):
        position = header + imports_offset + index * entry_sizes[imports_format]
        raw = struct.unpack_from("<I", data, position)[0]
        name = c_string(header + symbols_offset + (raw >> 9))
        if name == wanted:
            if raw & 0x100:
                raise RuntimeError(f"{wanted} is already weak in CPU slice 0x{cpu:x}")
            struct.pack_into("<I", data, position, raw | 0x100)
            import_matches += 1

    symbol_offset, symbol_count, string_offset, string_size = symtab
    symbol_matches = 0
    for index in range(symbol_count):
        position = base + symbol_offset + index * 16
        string_index, symbol_type, section, description, value = struct.unpack_from(
            "<IBBHQ", data, position
        )
        if string_index < string_size and c_string(base + string_offset + string_index) == wanted:
            if description & N_WEAK_REF:
                raise RuntimeError(f"{wanted} is already weak in the symbol table for CPU slice 0x{cpu:x}")
            struct.pack_into("<H", data, position + 6, description | N_WEAK_REF)
            symbol_matches += 1

    if import_matches != 1 or symbol_matches != 1:
        raise RuntimeError(
            f"unexpected {wanted} layout in CPU slice 0x{cpu:x}: "
            f"imports={import_matches}, symbols={symbol_matches}"
        )
    patched_slices += 1
    print(f"Patched CPU slice 0x{cpu:x}: chained import and symbol table")

if patched_slices == 0:
    raise RuntimeError("no Mach-O slices were patched")

output.write_bytes(data)
PY

original_owner="$(stat -f '%u:%g' "$APP/$FRAMEWORK_REL")"
original_mode="$(stat -f '%Lp' "$APP/$FRAMEWORK_REL")"
chown "$original_owner" "$work_dir/MAMachineLearning.patched"
chmod "$original_mode" "$work_dir/MAMachineLearning.patched"
cp -p "$work_dir/MAMachineLearning.patched" "$APP/$FRAMEWORK_REL"

bold "Signing the patched Logic app"
technical "Applying an ad-hoc signature to the copied application bundle."
codesign --force --deep --sign - "$APP"

bold "Verifying the patch"
technical "Checking the weak import and the application signature."
weak_count="$(xcrun dyld_info -imports "$APP/$FRAMEWORK_REL" 2>/dev/null | grep -F -c "$SYMBOL [weak-import]" || true)"
[[ "$weak_count" -ge 1 ]] || die "The weak-import verification failed."
codesign --verify --deep --strict "$APP"

PATCHED_CREATED=0
BACKUP_MOVED=0
trap 'rm -rf -- "$work_dir"' EXIT

bold "Logic Pro was patched successfully"
technical "Patched app: $APP"
technical "Original backup: $BACKUP"
technical "No system frameworks or SIP settings were changed."
