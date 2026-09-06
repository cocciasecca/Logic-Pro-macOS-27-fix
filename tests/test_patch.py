import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from macho_patch import patch, LayoutError
from bnns_probe import LEGACY, probe
from compat_patch import SHIM_LOAD_PATH, patch as compat_patch

def fixture(fmt=1, weak=False, cpu=0x100000c):
    d = bytearray(512)
    struct.pack_into('<8I', d, 0, 0xFEEDFACF, cpu, 0, 6, 2, 40, 0, 0)
    struct.pack_into('<6I', d, 32, 2, 24, 320, 1, 352, 64)
    struct.pack_into('<4I', d, 56, 0x80000034, 16, 128, 128)
    struct.pack_into('<7I', d, 128, 0, 0, 28, 64, 1, fmt, 0)
    bit = 1 << (16 if fmt == 3 else 8)
    struct.pack_into('<Q' if fmt == 3 else '<I', d, 156, 8 | (bit if weak else 0))
    symbol = b'_BNNSGraphGetSize\0'
    d[192:192+len(symbol)] = symbol
    struct.pack_into('<IBBHQ', d, 320, 1, 1, 0, 0x800 | (0x40 if weak else 0), 0)
    d[353:353+len(symbol)] = symbol
    return bytes(d)

class PatchTests(unittest.TestCase):
    def test_all_import_formats_only_expected_bytes(self):
        for fmt in (1, 2, 3):
            with self.subTest(fmt=fmt):
                old = fixture(fmt)
                new, report = patch(old)
                changes = {i for i, (a,b) in enumerate(zip(old,new)) if a != b}
                self.assertEqual(changes, {158 if fmt == 3 else 157, 326})
                self.assertEqual(new, fixture(fmt, True))
                self.assertFalse(report[0]['already_weak'])
    def test_idempotent(self):
        for fmt in (1,2,3):
            original = fixture(fmt, True)
            result, report = patch(original)
            self.assertEqual(result, original)
            self.assertTrue(report[0]['already_weak'])
    def test_fat_both_slices(self):
        head = bytearray(64)
        struct.pack_into('>2I', head, 0, 0xcafebabe, 2)
        struct.pack_into('>5I', head, 8, 0x1000007, 0, 64, 512, 0)
        struct.pack_into('>5I', head, 28, 0x100000c, 0, 576, 512, 0)
        result, report = patch(head + fixture(cpu=0x1000007) + fixture(3))
        self.assertEqual(len(report), 2)
        self.assertEqual(result[576:], fixture(3, True))
    def test_reject_truncations(self):
        for end in (0, 4, 31, 70, 180, 300, 370):
            with self.subTest(end=end), self.assertRaises(LayoutError):
                patch(fixture()[:end])
    def test_reject_bad_command(self):
        d = bytearray(fixture()); struct.pack_into('<I', d, 36, 0)
        with self.assertRaises(LayoutError): patch(d)
    def test_reject_bad_name_offset(self):
        d = bytearray(fixture()); struct.pack_into('<I', d, 156, 0xfffffe08)
        with self.assertRaises(LayoutError): patch(d)
    def test_reject_compression(self):
        d = bytearray(fixture()); struct.pack_into('<I', d, 152, 1)
        with self.assertRaises(LayoutError): patch(d)
    def test_reject_inconsistent_weak(self):
        d = bytearray(fixture()); struct.pack_into('<H', d, 326, 0x840)
        with self.assertRaises(LayoutError): patch(d)
    def test_reject_defined_symbol(self):
        d = bytearray(fixture()); d[324] = 0xf
        with self.assertRaises(LayoutError): patch(d)
    def test_reject_missing_target(self):
        d = fixture().replace(b'GraphGetSize', b'GraphGotSize')
        with self.assertRaises(LayoutError): patch(d)
    def test_probe_checks_every_symbol(self):
        checked = []
        def resolve(name):
            checked.append(name)
            return name != 'BNNSGraphOptionsCreateDefault'
        report = probe(resolve)
        self.assertEqual(checked, list(LEGACY))
        self.assertEqual(report['missing'], ['BNNSGraphOptionsCreateDefault'])
        self.assertFalse(report['legacy_surface_present'])
        self.assertFalse(report['abi_compatibility_verified'])

    def test_compat_patch_adds_shim_and_is_idempotent_on_real_binary(self):
        source = Path('/Applications/Logic Pro.app/Contents/Frameworks/MAMachineLearning.framework/Versions/A/MAMachineLearning')
        if not source.exists():
            self.skipTest('Logic Pro test binary is not installed')
        original = source.read_bytes()
        patched, report = compat_patch(original)
        self.assertIn(b'@loader_path/BNNSCompat.dylib', patched)
        self.assertNotIn(b'/System/Library/Frameworks/Accelerate.framework/Accelerate\0', patched)
        self.assertEqual(len(report), 2)
        self.assertTrue(all(x['load_command_added'] for x in report))
        self.assertTrue(all(x['dlopen_string_patched'] for x in report))
        again, second_report = compat_patch(patched)
        self.assertEqual(again, patched)
        self.assertTrue(all(not x['load_command_added'] for x in second_report))
        self.assertTrue(all(not x['dlopen_string_patched'] for x in second_report))

    def test_compat_patch_uses_real_dyld_library_ordinal(self):
        source = Path('/Applications/Logic Pro.app/Contents/Frameworks/MAMachineLearning.framework/Versions/A/MAMachineLearning')
        if not source.exists():
            self.skipTest('Logic Pro test binary is not installed')
        _, report = compat_patch(source.read_bytes())
        self.assertEqual({x['shim_ordinal'] for x in report}, {21})
        self.assertTrue(all(x['shim_ordinal'] > 13 for x in report))

if __name__ == '__main__': unittest.main()
