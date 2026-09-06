# Attestazione tecnica sul contenuto della repository

Data: 2026-09-06

Repository: `Logic-Pro-macOS-27-fix-clean`

Questa repository contiene un fix sperimentale per Logic Pro 11.2.2 su macOS
27.0 (26A5425a), relativo alla rimozione di simboli legacy BNNS usati da
`MAMachineLearning.framework`.

## Contenuto incluso

- codice sorgente C della shim `BNNSCompat.dylib`;
- script shell e Python per diagnosi e patch diretta con backup;
- test locali;
- documentazione tecnica e README.

## Contenuto non incluso

Questa repository pulita non include:

- `libBNNS.dylib` di Apple;
- file estratti dal dyld shared cache di macOS;
- copie di `Logic Pro.app`;
- framework o binari Apple redistribuiti;
- archivi o librerie estratti da altri Mac;
- report di crash completi con identificativi personali;
- dati personali, username, file utente o contenuti provenienti dal Mac di terzi.

La libreria `BNNSCompat.dylib` non viene distribuita già compilata: viene generata
localmente dagli script a partire dal sorgente `shim/bnns_compat.c`.

## Verifiche eseguite

Sono state eseguite le seguenti verifiche locali:

- test unitari Python: 13 test superati;
- controllo sintattico degli script `.command`;
- compilazione della shim come libreria universale `arm64` e `x86_64`;
- smoke test nativo su un modello `.mil` reale incluso nell’installazione locale
  di Logic Pro;
- verifica che il framework patchato punti a `@loader_path/BNNSCompat.dylib`;
- verifica che la stringa interna di `dlopen` verso `Accelerate` venga
  rediretta verso la shim;
- verifica che non siano presenti nella shim stringhe contenenti percorsi utente
  o username locali.

## Nota

Questa attestazione è tecnica, non legale. Descrive il contenuto e le verifiche
effettuate sulla copia pulita della repository al momento della preparazione.

Firmato,

Codex
