# Investigation — 2026-09-06

## Observed, not assumed

Environment: Logic 11.2.2 (6387), macOS 27.0 build 26A5425a, arm64.
Repository base and working branch are recorded by git. No Apple binaries or
private crash reports are committed.

- The installed framework still has a strong `_BNNSGraphGetSize` import in both
  slices. The fresh startup report is a DYLD missing-symbol termination.
- Six older local crash reports have PC=0, with the first framework frame at
  `Mil2BNNSModel::compileOrLoadBNNSIRs(bool)+72`, offset `0xae38`.
- In the inspected arm64 framework, `0xae30` loads the pointer at `0x2dfc0`, and
  `0xae34` calls it. That pointer is populated by resolving
  `BNNSGraphOptionsCreateDefault`. These crashes therefore occur before GetSize.
- The constructor calls both BNNS initializers at `0xca04` and `0xca08` and ignores
  their return values before calling compilation. Weak import does not populate
  the missing function pointers.
- Direct symbol resolution reports 13/14 requested names absent. The remaining
  `BNNSGraphGetArgumentPosition` name resolving does not establish old ABI parity.
- The only direct GetSize call found in this arm64 framework is at `0xc67c`.
  There are also indirect SPI wrappers; fixing this one instruction is insufficient.
- Historical stacks pass through `CMLSaturation`, `CMLSaturationFX`, and
  `CMLSaturationShell::OnSetup`. They do not, by themselves, establish which user
  action (MIDI, Drummer or another preset) triggered each report.

## Why simple interposition/aliases are insufficient

The library uses both a two-level Mach-O import from Accelerate and `dlsym` on an
explicit Accelerate handle. Exporting one symbol in an arbitrary dylib does not
necessarily satisfy both resolution paths. An eventual adapter must redirect
both deliberately, with a loader integration test; relying on
`DYLD_INSERT_LIBRARIES` alone is not a verified installation strategy.

Current SDK types `bnns_graph_t`, `bnns_graph_context_t` and compile options contain
both a pointer and a size. The legacy call at `0xc658` passes format 10, a filename,
NULL and a pointer to options. The current compile API takes filename, function
and a two-word options object, and returns a two-word graph. Renaming its import
to `_BNNSGraphCompileFromFile_v2` is ABI-incompatible.

`BNNSGraphGetSize` refers to serialized graph size, not the workspace allocation.
Returning zero, a guessed constant or `BNNSGraphContextGetWorkspaceSize` would not
supply the required semantics. The observed legacy execute call at `0xc2ec`
passes a graph pointer, a pointer array and workspace; current context execution
requires a context, argument count/descriptors and workspace size as well.

References: [Apple BNNS documentation](https://developer.apple.com/documentation/accelerate/bnns-library/)
and [context workspace size](https://developer.apple.com/documentation/accelerate/bnnsgraphcontextgetworkspacesize(_:_:)).
The local SDK `BNNS/bnns_graph.h` and disassembly supply the ABI evidence above.

## Implemented route that retains ML

A legacy-to-current BNNS adapter, scoped to the exact Logic framework, is more
defensible than suppressing errors or changing function names. The implemented
candidate builds `BNNSCompat.dylib`, places it next to the patched
MAMachineLearning binary and makes Logic's framework resolve both paths through
the shim:

- the direct two-level `_BNNSGraphGetSize` Mach-O import is moved from
  `Accelerate` to `@loader_path/BNNSCompat.dylib`;
- the explicit `dlopen("/System/Library/Frameworks/Accelerate.framework/Accelerate")`
  string used by the private BNNS initializer is redirected to the same shim;
- the shim re-exports Accelerate and translates the removed legacy graph calls to
  the current graph API, based on the macOS 26 wrapper behavior supplied by the
  external reference report.

Implemented proof: FSQ 44.1 kHz, 512-frame transformed MIL:
629850 graph bytes, 24 inputs, 23 outputs, 47 arguments; three executions with
initially zero buffers returned success and finite Float32 buffers; workspace
2530304 bytes. Enclosing directory compilation failed; the actual MIL succeeded.
This is **not an audio-equivalence test**. The new `legacy_bnns_smoke` test loads
the shim itself, verifies the 14 legacy names resolve through it, and compiles the
same MIL through the legacy ABI surface. It does not launch Logic or exercise
CoreAudio, MIDI import, Drummer track creation, model switches or real-time audio
callbacks.

Per user preference, ChromaGlow/ML has not been bypassed or disabled.

## Patcher improvements actually implemented

- Read-only full-symbol diagnosis is the default; missing symbols exit 2.
- Separate pure Python parsers with bounded reads, exact match counts,
  unsupported-format rejection and idempotence.
- Correct format-3 chained import layout (64-bit word, bit 16 weak flag,
  name offset at bit 32), rather than treating it as format 1.
- No moving/deleting the installed app or its backup; explicit prepare mode stages
  a separate destination, signs, verifies all slices and publishes last.
- Removed the shell rollback's `status` variable (read-only special parameter in
  zsh) and separated signal exits from normal cleanup.
- Added regression tests, a native public compile/inference probe and a native
  legacy shim smoke test.

Validation: 13 Python tests, real two-slice binary patch, dyld import inspection
and the legacy shim smoke test passed. Native probes built with warnings as
errors and passed the MIL tests described above. Full app copy/signing passed for
`Logic-BNNS-Test-2.app`; Logic GUI, MIDI, Drummer and audio parity remain
untested.
