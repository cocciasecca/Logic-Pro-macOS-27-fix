#!/usr/bin/env python3
"""Patch MAMachineLearning to use the local BNNS compatibility shim."""
import argparse
import struct
from pathlib import Path

ACCELERATE_DLOPEN = b"/System/Library/Frameworks/Accelerate.framework/Accelerate"
SHIM_LOAD_PATH = b"@loader_path/BNNSCompat.dylib"
TARGET_SYMBOL = b"_BNNSGraphGetSize"
LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_LOAD_UPWARD_DYLIB = 0x80000023
LC_LAZY_LOAD_DYLIB = 0x20
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_DYLD_CHAINED_FIXUPS = 0x80000034
CPU_X86_64 = 0x1000007
CPU_ARM64 = 0x100000C


class PatchError(ValueError):
    pass


def _align(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)


def _unpack(data, fmt, pos, lo, hi):
    size = struct.calcsize(fmt)
    if pos < lo or pos + size > hi:
        raise PatchError("out-of-bounds Mach-O data")
    return struct.unpack_from(fmt, data, pos)


def _cstring(data, pos, lo, hi):
    if pos < lo or pos >= hi:
        raise PatchError("out-of-bounds string")
    end = data.find(b"\0", pos, hi)
    if end < 0:
        raise PatchError("unterminated string")
    return bytes(data[pos:end])


def _slices(data):
    magic = bytes(data[:4])
    if magic == b"\xca\xfe\xba\xbe":
        count, = _unpack(data, ">I", 4, 0, len(data))
        if count < 1 or count > 32:
            raise PatchError("invalid fat slice count")
        out = []
        for index in range(count):
            cpu, _, offset, size, _ = _unpack(data, ">5I", 8 + 20 * index, 0, len(data))
            if size < 32 or offset + size > len(data):
                raise PatchError("invalid fat slice bounds")
            out.append((cpu, offset, size))
        return out
    if magic == b"\xcf\xfa\xed\xfe":
        cpu, = _unpack(data, "<I", 4, 0, len(data))
        return [(cpu, 0, len(data))]
    raise PatchError("unsupported Mach-O container")


def _load_commands(data, base, size):
    hi = base + size
    magic, cpu, _, _, ncmds, sizeofcmds, _, _ = _unpack(data, "<8I", base, base, hi)
    if magic != 0xFEEDFACF or cpu not in (CPU_X86_64, CPU_ARM64):
        raise PatchError("unsupported Mach-O slice")
    start = base + 32
    end = start + sizeofcmds
    if end > hi:
        raise PatchError("invalid load-command bounds")
    commands = []
    cursor = start
    for _ in range(ncmds):
        cmd, cmdsize = _unpack(data, "<II", cursor, start, end)
        if cmdsize < 8 or cmdsize % 8 or cursor + cmdsize > end:
            raise PatchError("invalid load command")
        commands.append((cursor, cmd, cmdsize))
        cursor += cmdsize
    if cursor != end:
        raise PatchError("inconsistent load-command size")
    return commands, ncmds, sizeofcmds


def _first_section_file_offset(data, base, size, commands):
    first = base + size
    for pos, cmd, cmdsize in commands:
        if cmd != LC_SEGMENT_64:
            continue
        nsects, = _unpack(data, "<I", pos + 64, pos, pos + cmdsize)
        section = pos + 72
        for _ in range(nsects):
            fileoff, = _unpack(data, "<I", section + 48, pos, pos + cmdsize)
            if fileoff:
                first = min(first, base + fileoff)
            section += 80
    return first


def _cstring_ranges(data, base, commands):
    ranges = []
    for pos, cmd, cmdsize in commands:
        if cmd != LC_SEGMENT_64:
            continue
        nsects, = _unpack(data, "<I", pos + 64, pos, pos + cmdsize)
        section = pos + 72
        for _ in range(nsects):
            sectname = bytes(data[section:section + 16]).split(b"\0", 1)[0]
            segname = bytes(data[section + 16:section + 32]).split(b"\0", 1)[0]
            section_size, section_offset = _unpack(data, "<QI", section + 40, pos, pos + cmdsize)
            if sectname == b"__cstring" and segname == b"__TEXT":
                ranges.append((base + section_offset, base + section_offset + section_size))
            section += 80
    if not ranges:
        raise PatchError("missing __TEXT,__cstring section")
    return ranges


def _dylib_ordinals(data, commands):
    out = []
    for pos, cmd, cmdsize in commands:
        if cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB, LC_LAZY_LOAD_DYLIB):
            name_offset, = _unpack(data, "<I", pos + 8, pos, pos + cmdsize)
            out.append(_cstring(data, pos + name_offset, pos, pos + cmdsize))
    return out


def _append_load_dylib(data, base, size, path):
    commands, ncmds, sizeofcmds = _load_commands(data, base, size)
    dylibs = _dylib_ordinals(data, commands)
    if path in dylibs:
        return dylibs.index(path) + 1, False
    command_size = _align(24 + len(path) + 1, 8)
    load_end = base + 32 + sizeofcmds
    first_section = _first_section_file_offset(data, base, size, commands)
    if load_end + command_size > first_section:
        raise PatchError("not enough Mach-O header padding for shim load command")
    if any(data[load_end:first_section]):
        raise PatchError("non-empty header padding")
    command = bytearray(command_size)
    struct.pack_into("<6I", command, 0, LC_LOAD_DYLIB, command_size, 24, 0, 0x10000, 0x10000)
    command[24:24 + len(path)] = path
    data[load_end:load_end + command_size] = command
    struct.pack_into("<II", data, base + 16, ncmds + 1, sizeofcmds + command_size)
    return len(dylibs) + 1, True


def _patch_direct_import(data, base, size, new_ordinal):
    commands, _, _ = _load_commands(data, base, size)
    symtab = fixups = None
    for pos, cmd, cmdsize in commands:
        if cmd == LC_SYMTAB:
            symtab = _unpack(data, "<4I", pos + 8, pos, pos + cmdsize)
        if cmd == LC_DYLD_CHAINED_FIXUPS:
            fixups = _unpack(data, "<2I", pos + 8, pos, pos + cmdsize)
    if not symtab or not fixups:
        raise PatchError("missing symbol table or chained fixups")

    offset, length = fixups
    start, stop = base + offset, base + offset + length
    version, _, imports, symbols, count, fmt, compression = _unpack(data, "<7I", start, start, stop)
    if version != 0 or compression != 0 or fmt not in (1, 2, 3):
        raise PatchError("unsupported chained import format")
    entry_size = {1: 4, 2: 8, 3: 16}[fmt]
    import_matches = []
    for index in range(count):
        pos = start + imports + index * entry_size
        raw, = _unpack(data, "<Q" if fmt == 3 else "<I", pos, start, stop)
        name_offset = raw >> (32 if fmt == 3 else 9)
        if _cstring(data, start + symbols + name_offset, start + symbols, stop) == TARGET_SYMBOL:
            import_matches.append((pos, raw, "<Q" if fmt == 3 else "<I"))
    if len(import_matches) != 1:
        raise PatchError("expected exactly one chained import for BNNSGraphGetSize")
    pos, raw, encoding = import_matches[0]
    if fmt == 3:
        raw = (raw & ~0x1FFFF) | new_ordinal
    else:
        raw = (raw & ~0x1FF) | new_ordinal
    struct.pack_into(encoding, data, pos, raw)

    symoff, nsyms, stroff, strsize = symtab
    sym_matches = []
    for index in range(nsyms):
        pos = base + symoff + index * 16
        idx, typ, section, desc, value = _unpack(data, "<IBBHQ", pos, base, base + size)
        if _cstring(data, base + stroff + idx, base + stroff, base + stroff + strsize) == TARGET_SYMBOL:
            if typ & 0xE0 or (typ & 0x0E) != 0 or not typ & 1 or section or value:
                raise PatchError("BNNSGraphGetSize is not an external undefined symbol")
            sym_matches.append((pos, desc))
    if len(sym_matches) != 1:
        raise PatchError("expected exactly one undefined symbol for BNNSGraphGetSize")
    sym_pos, desc = sym_matches[0]
    struct.pack_into("<H", data, sym_pos + 6, (desc & ~0xFF40) | (new_ordinal << 8))


def _patch_dlopen_path(data, base, size):
    commands, _, _ = _load_commands(data, base, size)
    hits = []
    patched_hits = []
    needle = ACCELERATE_DLOPEN + b"\0"
    replacement = SHIM_LOAD_PATH + b"\0"
    for lo, hi in _cstring_ranges(data, base, commands):
        cursor = lo
        while True:
            found = data.find(needle, cursor, hi)
            if found < 0:
                break
            hits.append(found)
            cursor = found + 1
        cursor = lo
        while True:
            found = data.find(replacement, cursor, hi)
            if found < 0:
                break
            patched_hits.append(found)
            cursor = found + 1
    if not hits:
        if len(patched_hits) == 1:
            return False
        raise PatchError("explicit Accelerate dlopen string was not found")
    if patched_hits:
        raise PatchError("mixed original and patched dlopen strings")
    if len(hits) != 1:
        raise PatchError("expected exactly one explicit Accelerate dlopen string")
    pos = hits[0]
    data[pos:pos + len(needle)] = replacement + (b"\0" * (len(needle) - len(replacement)))
    return True


def patch(source, shim_path=SHIM_LOAD_PATH):
    data = bytearray(source)
    report = []
    for cpu, base, size in _slices(data):
        ordinal, added = _append_load_dylib(data, base, size, shim_path)
        _patch_direct_import(data, base, size, ordinal)
        dlopen_patched = _patch_dlopen_path(data, base, size)
        report.append({
            "cpu": hex(cpu),
            "shim_ordinal": ordinal,
            "load_command_added": added,
            "dlopen_string_patched": dlopen_patched,
        })
    return bytes(data), report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result, report = patch(args.source.read_bytes())
    with args.output.open("xb") as stream:
        stream.write(result)
    print(report)


if __name__ == "__main__":
    main()
