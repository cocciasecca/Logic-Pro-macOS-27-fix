# Logic Pro macOS 27 BNNS Fix

Fix sperimentale per Logic Pro 11.2.2 su macOS 27.0, dove Logic crasha per il
simbolo BNNS mancante `_BNNSGraphGetSize`.

## Uso

Chiudi Logic Pro, poi lancia:

```sh
./patch-logic-bnns.command
```

Lo script:

- compila localmente `BNNSCompat.dylib`;
- prepara una copia patchata di Logic;
- salva un backup di `/Applications/Logic Pro.app`;
- installa la copia patchata come app principale;
- verifica la firma.

Il backup viene salvato con un nome tipo:

```text
/Applications/Logic Pro.app.BNNS-backup-YYYYMMDD-HHMMSS
```

## Diagnosi

Per controllare i simboli BNNS senza modificare Logic:

```sh
./patch-logic-bnns.command --diagnose
```

## Cosa Testare

Dopo la patch:

- apri Logic;
- apri o importa il MIDI che prima crashava;
- crea o seleziona Batteria/Drummer;
- prova anche ChromaGlow o altri effetti ML.

Se crasha ancora, conserva il nuovo crash report: serve per capire il prossimo
punto da correggere.

## Note

La repo non contiene librerie Apple, copie di Logic, file estratti da macOS o
dati personali. `BNNSCompat.dylib` viene compilata sul Mac dell'utente partendo
dal sorgente `shim/bnns_compat.c`.
