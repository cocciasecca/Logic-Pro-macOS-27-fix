#!/usr/bin/env python3
"""Validated weak-import patch. This addresses loading ONLY, not BNNS ABI removal."""
import argparse
import struct
from pathlib import Path

class LayoutError(ValueError):
    pass

def patch(source, wanted='_BNNSGraphGetSize'):
    data = bytearray(source)
    def bounds(pos, count, lo=0, hi=None):
        hi = len(data) if hi is None else hi
        if pos < lo or count < 0 or pos + count > hi:
            raise LayoutError('out-of-bounds Mach-O data')
    def unpack(fmt, pos, lo=0, hi=None):
        bounds(pos, struct.calcsize(fmt), lo, hi)
        return struct.unpack_from(fmt, data, pos)
    def string(pos, lo, hi):
        bounds(pos, 1, lo, hi)
        end = data.find(0, pos, hi)
        if end < 0:
            raise LayoutError('unterminated string')
        return bytes(data[pos:end])
    magic = bytes(data[:4])
    slices = []
    if magic == b'\xca\xfe\xba\xbe':
        count, = unpack('>I', 4)
        if count < 1 or count > 32:
            raise LayoutError('invalid slice count')
        bounds(8, count * 20)
        for i in range(count):
            cpu, _, base, size, _ = unpack('>5I', 8 + 20*i)
            bounds(base, size, 8 + 20*count)
            if size < 32 or any(base < b+s and b < base+size for _, b, s in slices):
                raise LayoutError('invalid or overlapping slices')
            slices.append((cpu, base, size))
    elif magic == b'\xcf\xfa\xed\xfe':
        slices = [(unpack('<I', 4)[0], 0, len(data))]
    else:
        raise LayoutError('unsupported Mach-O format')
    report = []
    for cpu, base, size in slices:
        hi = base+size
        m, actual_cpu, _, _, ncmds, sizeofcmds, _, _ = unpack('<8I', base, base, hi)
        if m != 0xFEEDFACF or actual_cpu != cpu or cpu not in (0x1000007, 0x100000c):
            raise LayoutError('unsupported CPU or header')
        cursor, end = base+32, base+32+sizeofcmds
        bounds(cursor, sizeofcmds, base, hi)
        symtab = fixups = None
        for _ in range(ncmds):
            cmd, length = unpack('<II', cursor, base+32, end)
            if length < 8 or length % 8:
                raise LayoutError('invalid load command size')
            bounds(cursor, length, base+32, end)
            if cmd == 2:
                if symtab or length != 24: raise LayoutError('invalid symbol command')
                symtab = unpack('<4I', cursor+8, cursor, cursor+length)
            if cmd == 0x80000034:
                if fixups or length != 16: raise LayoutError('invalid fixups command')
                fixups = unpack('<2I', cursor+8, cursor, cursor+length)
            cursor += length
        if cursor != end or symtab is None or fixups is None:
            raise LayoutError('missing or inconsistent load commands')
        offset, length = fixups
        start, stop = base+offset, base+offset+length
        bounds(start, length, base, hi)
        version, _, imports, symbols, count, fmt, compression = unpack('<7I', start, start, stop)
        if version != 0 or compression != 0 or fmt not in (1, 2, 3):
            raise LayoutError('unsupported chained fixups encoding')
        entry_size = {1:4, 2:8, 3:16}[fmt]
        bounds(start+imports, count*entry_size, start+28, stop)
        if symbols < imports+count*entry_size:
            raise LayoutError('overlapping imports and strings')
        bounds(start+symbols, 1, start+28, stop)
        matches = []
        for i in range(count):
            pos = start+imports+i*entry_size
            raw, = unpack('<Q' if fmt == 3 else '<I', pos, start, stop)
            name_offset = raw >> (32 if fmt == 3 else 9)
            if string(start+symbols+name_offset, start+symbols, stop) == wanted.encode():
                bit = 1 << (16 if fmt == 3 else 8)
                matches.append((pos, raw, bit, '<Q' if fmt == 3 else '<I'))
        symoff, nsyms, stroff, strsize = symtab
        bounds(base+symoff, nsyms*16, base, hi)
        bounds(base+stroff, strsize, base, hi)
        smatches = []
        for i in range(nsyms):
            pos = base+symoff+i*16
            idx, typ, section, desc, value = unpack('<IBBHQ', pos, base, hi)
            if string(base+stroff+idx, base+stroff, base+stroff+strsize) == wanted.encode():
                if typ & 0xe0 or (typ & 0x0e) != 0 or not typ & 1 or section or value:
                    raise LayoutError('target is not an external undefined symbol')
                smatches.append((pos, desc))
        if len(matches) != 1 or len(smatches) != 1:
            raise LayoutError('expected exactly one import and undefined symbol per slice')
        pos, raw, bit, encoding = matches[0]
        spos, desc = smatches[0]
        if bool(raw & bit) != bool(desc & 0x40):
            raise LayoutError('inconsistent weak-import flags')
        already = bool(raw & bit)
        struct.pack_into(encoding, data, pos, raw | bit)
        struct.pack_into('<H', data, spos+6, desc | 0x40)
        report.append({'cpu': hex(cpu), 'already_weak': already})
    return bytes(data), report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result, report = patch(args.source.read_bytes())
    # Exclusive creation; never overwrite source, a backup, or a previous result.
    with args.output.open('xb') as stream:
        stream.write(result)
    print(report)

if __name__ == '__main__':
    main()
