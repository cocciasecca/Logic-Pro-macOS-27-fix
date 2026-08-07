# Logic Pro BNNS Weak-Import Patch

An unofficial compatibility patch for a Logic Pro startup crash caused by a missing `_BNNSGraphGetSize` symbol.

Tested with:

- Logic Pro 11.2.2
- macOS 27.0 beta
- Apple Silicon

The original crash looks similar to this:

```text
dyld: Symbol not found: _BNNSGraphGetSize
Referenced from: MAMachineLearning.framework
Expected in: Accelerate.framework
```

## Usage

Download `patch-logic-bnns.command`, then run:

```bash
chmod +x ~/Downloads/patch-logic-bnns.command
~/Downloads/patch-logic-bnns.command
```

Enter your administrator password when macOS asks for it. Terminal does not display password characters while you type; this is normal.

After the script reports success, launch Logic Pro normally from `/Applications`.

## What the patch does

The script changes `_BNNSGraphGetSize` in Logic's bundled `MAMachineLearning.framework` from a strong import to a weak import.

It patches both the Apple Silicon and Intel slices when they are present, then applies an ad-hoc signature and verifies the resulting application bundle.

The script does **not** disable SIP and does **not** modify macOS or any system framework.

## Safety and backup

Before patching, the script moves the original installation:

```text
/Applications/Logic Pro.app
```

to:

```text
/Applications/Logic Pro.app.bak
```

It then creates the patched copy at the original application path. If patching or verification fails, the script attempts to restore the original automatically.

The script stops without changing anything if `Logic Pro.app.bak` already exists.

## Restoring the original application

Quit Logic Pro, then run:

```bash
sudo rm -rf "/Applications/Logic Pro.app"
sudo mv "/Applications/Logic Pro.app.bak" "/Applications/Logic Pro.app"
```

Check both paths carefully before running the restoration commands.

## Important notes

- This is an unofficial workaround and is not affiliated with or supported by Apple.
- Keep the `.app.bak` backup until you are certain everything you need works.
- The patched application uses an ad-hoc signature rather than Apple's original signature.
- Updating or reinstalling Logic Pro will probably require applying the patch again.
- Features that actually require the missing BNNS function may still fail, even if Logic starts normally.
- The patcher validates the expected Mach-O structure and aborts instead of applying an unknown layout.
- Use this software at your own risk and keep backups of important projects.

## Technical summary

`MAMachineLearning.framework` contains a two-level, strong import of `_BNNSGraphGetSize` from `Accelerate.framework`. On affected systems the symbol is unavailable, so `dyld` aborts before Logic can finish launching.

The patch sets the weak-import flag in both the chained-import record and the matching Mach-O symbol-table entry for every supported 64-bit slice. No function implementation is injected and no system binary is replaced.
