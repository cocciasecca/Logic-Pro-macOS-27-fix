# Logic Pro 11.2.2 / macOS 27 BNNS investigation

This revision replaces the old startup-only workaround with a scoped BNNS
compatibility shim for Logic Pro 11.2.2 on macOS 27.0 (26A5425a). The shim
exports the legacy BNNS graph symbols that MAMachineLearning expects, translates
the calls to the current macOS 27 BNNS Graph API where possible, and keeps ML
effects available for testing.

This is still a field candidate. Logic GUI, MIDI import and Drummer must be
tested manually on the affected machine before calling it fixed.

## Diagnose without changing Logic

Clone/download the **whole repository**, then run:

```sh
./patch-logic-bnns.command --diagnose
```

The default action is also diagnosis. It resolves all 14 legacy symbols requested
by MAMachineLearning's two BNNS initializers in the current process architecture.
Exit status 2 means at least one is missing; 0 means all names resolve, **not**
that their ABI or Logic's audio operation has been verified. Other failures are
reported as errors. No administrator password is needed.

On macOS 27.0 (26A5425a), Apple Silicon, 13 symbols were missing. Historical local
crashes show a null call to `BNNSGraphOptionsCreateDefault` during
`Mil2BNNSModel::compileOrLoadBNNSIRs`, reached through `CMLSaturation`.
See [INVESTIGATION.md](INVESTIGATION.md) for evidence and the proposed adapter.

## Public BNNS model test, without launching Logic

Requires Apple's Command Line Tools and a macOS SDK with BNNS Graph APIs:

```sh
mkdir -p build
xcrun clang -Wall -Wextra -Werror -framework Accelerate \
  tools/modern_bnns_probe.c -o build/modern_bnns_probe
build/modern_bnns_probe "/Applications/Logic Pro.app/Contents/Frameworks/MAMachineLearning.framework/Versions/A/Resources/FSQ_44_i2ib8ecc9q_0881.mlmodelc/model_512_transformed.mil"
```

The probe compiles the supplied model, queries argument tensors, allocates buffers
with a 512 MiB aggregate limit (excluding compiler/graph internal allocations),
and executes three times with initially zeroed buffers. It checks finite Float32
buffers. It does not emit audio or modify the app. A successful result does not
prove numerical parity, state continuity, real-time performance, or old-ABI
compatibility. Use the `.mil` file in the example: passing just its enclosing
`.mlmodelc` directory failed in this environment.

## Prepare a test copy

This does not change `/Applications/Logic Pro.app`. It prepares a separately
named copy, patches that copy's MAMachineLearning framework to load
`BNNSCompat.dylib`, signs it ad hoc, and verifies the result:

```sh
./patch-logic-bnns.command --prepare "$PWD/Logic-BNNS-Test.app"
```

The destination must not exist and must be outside `/Applications` and the source
app. Set `LOGIC_APP` to inspect/copy another installation. Existing
installations, backups, system frameworks and SIP settings are left alone. The
resulting copy has an ad-hoc signature. Do not use it to save changes to
valuable projects.

Before copying, the script builds the shim and runs a native smoke test against a
bundled Logic MIL model. After signing, it re-parses the patched framework and
confirms the patch is idempotent.

## Install over the main app with backup

After the test copy is known to launch on your machine, this script prepares a
fresh patched copy, verifies it, backs up the current `/Applications/Logic Pro.app`
with a timestamped name, then installs the patched copy as the main app:

```sh
./install-logic-bnns.command
```

It refuses to run while Logic is open. The backup is named like
`/Applications/Logic Pro.app.BNNS-backup-YYYYMMDD-HHMMSS`. If installation fails
after the original app was moved, the script attempts to restore the backup.

## Tests

```sh
python3 -m unittest discover -s tests -v
zsh -n patch-logic-bnns.command
zsh -n install-logic-bnns.command
```

Local results: 13 unit tests passed; actual universal MAMachineLearning patched
in a scratch copy; `_BNNSGraphGetSize` now resolves from
`@loader_path/BNNSCompat.dylib` at dyld ordinal 21 in both slices; the explicit Accelerate `dlopen`
string was redirected to the shim; and the legacy shim smoke test compiled a
bundled MIL model with 629850 graph bytes, 24 inputs, 23 outputs and 2530304
workspace bytes. Logic was not launched. Full GUI behavior was not tested.

## Manual acceptance checklist

1. Quit every Logic instance; explicitly open the candidate app and confirm its
   path/version. Use a duplicate project and note the audio device, buffer size
   and sample rate.
2. Open the exact MIDI file that previously crashed, then import it into an empty
   project. Play, stop, seek, save a new copy, close and reopen it.
3. Create a Drummer track; select the same drum kit/preset that crashed, switch
   kits, generate a region and play it. Also test a software-instrument drum kit.
4. Verify ChromaGlow/ML saturation remains functional: toggle bypass, change its
   model/style and drive, listen for expected changes, and bounce a short passage.
   Passing MIDI/Drummer with the ML effect missing or silent is **not a pass**.
5. Repeat at the working sample rates and buffer sizes; check CPU load, dropouts
   and latency. Compare against a known-good OS/app if available.
6. If it crashes, preserve the new `.ips`, the exact reproduction steps and which
   candidate was launched. Do not label unrelated crash stacks as the same bug.

Passing this checklist is the real proof. The local tests only prove that the
binary patch and BNNS translation layer are coherent enough to load and compile a
real bundled model outside Logic.

## Collect a working reference Mac

Send `tools/collect-bnns-reference.command` to an Apple Silicon Mac running an older macOS. Run it with `zsh collect-bnns-reference.command`. It writes a text report next to the script with OS build, standard-path Logic version and resolution/owner of the 14 legacy symbols. It compiles a temporary arm64 probe if Command Line Tools are already available; otherwise it collects a partial report. No administrator access, Logic launch, library extraction, serial numbers or projects are involved. Symbol presence does not prove ABI compatibility.
