# Changelog

## 1.0.0 - 2026-10-25

Prima versione pubblica.

- Generazione di file `.tap` con bootstrap KERNAL, turbo loader a interrupt e blocchi con checksum.
- Schermata di caricamento: titolo arcobaleno, barra di avanzamento con percentuale, bordo sincronizzato con i dati,
  scritta fissa in alto e descrizione a pagine (fino a 10 righe da 38 caratteri).
- Musica: file SID, musica predefinita o nessuna musica.
- Rilocazione automatica o manuale del SID, con analisi della memoria di lavoro e della zero page, e verifica con
  emulatore 6502 incorporato; pulsante per proporre l'indirizzo ideale.
- Controlli sui file e sulla memoria prima della generazione, con mappa di memoria colorata.
- Preset per emulatore (veloce/standard) e per datassette originale (normale/sicuro).
- Interfaccia grafica (tkinter) e riga di comando (`--check`, `--preset`, `--music`, `--sid-reloc`, ...).
- Schermata di errore con diagnostica (`BLOCCHI xx/yy ERR zz`).
- Esempio incluso in `examples/`.
