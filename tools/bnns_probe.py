#!/usr/bin/env python3
"""Read-only probe: resolve every SPI used by Logic's BNNS initializers."""
import argparse
import ctypes
import json
import platform
import plistlib
from pathlib import Path

LEGACY = (
    'BNNSGraphCompileFromFile', 'BNNSGraphExecute',
    'BNNSGraphOptionsCreateDefault', 'BNNSGraphOptionsSetSingleThread',
    'BNNSGraphGetWorkspaceSize', 'BNNSGraphGetSize',
    'BNNSGraphContextGetArgPosition', 'BNNSGraphGetNumInputs',
    'BNNSGraphGetInputNames', 'BNNSGraphGetNumOutputs',
    'BNNSGraphGetOutputNames', 'BNNSGraphGetTensorDescriptor',
    'BNNSGraphOptionsSetPredefinedOptimizations', 'BNNSGraphGetArgumentPosition',
)
ACCELERATE = '/System/Library/Frameworks/Accelerate.framework/Accelerate'

def probe(resolver):
    result = {name: bool(resolver(name)) for name in LEGACY}
    return {'symbols': result, 'missing': [n for n, found in result.items() if not found],
            'legacy_surface_present': all(result.values()),
            'abi_compatibility_verified': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=Path('/Applications/Logic Pro.app'))
    args = parser.parse_args()
    lib = ctypes.CDLL(ACCELERATE)
    report = probe(lambda n: getattr(lib, n, None))
    report.update(machine=platform.machine(), macos=platform.mac_ver()[0])
    info = args.app / 'Contents/Info.plist'
    if info.exists():
        with info.open('rb') as stream:
            d = plistlib.load(stream)
        report['logic'] = {k: d.get(k) for k in ('CFBundleShortVersionString', 'CFBundleVersion')}
    print(json.dumps(report, indent=2))
    return 2 if report['missing'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
