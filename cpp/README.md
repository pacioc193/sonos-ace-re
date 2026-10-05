# ace.exe – client Windows (C++/WinRT)

Console app Win32 che parla con le Sonos Ace via BLE (GATT). Non serve compilare: la
GitHub Action `build` produce l'exe a ogni push e lo pubblica nella Release **latest**
(link diretto: `https://github.com/pacioc193/sonos-ace-re/releases/download/latest/ace.exe`;
il repo è privato, quindi serve essere loggati su GitHub).

Requisiti: Windows 10 1709+ / Windows 11 con Bluetooth LE, cuffie già associate a Windows.
**Chiudi l'app Sonos sul telefono** (o disattiva il Bluetooth del telefono) prima di provare:
le cuffie potrebbero accettare un solo collegamento di controllo alla volta.

## Primo test (in quest'ordine)

```bat
ace.exe list                       :: dispositivi associati, con nome e id
ace.exe scan                       :: annunci BLE (cerca "Sonos Ace")
ace.exe auto services              :: UUID e handle GATT di tutti i servizi
ace.exe auto probe                 :: tutte le letture, con risposta decodificata
ace.exe auto get anc               :: modalità attuale
ace.exe auto mode aware            :: trasparenza (anc | aware | off)
ace.exe auto bass 4                :: -10..10, idem treble e balance
ace.exe auto sniff 30              :: ascolta gli eventi (cambia volume/modalità dalle cuffie)
```

`auto` cerca un dispositivo associato con "sonos ace" nel nome; si può passare anche
l'indirizzo (`80:4A:F2:05:AF:27`) o parte del nome.

## Debug

Il log è **completo di default**: ogni passo, codice di stato Windows/GATT, handle e byte
inviati/ricevuti, con orario, sia a console sia nel file `ace_debug_<data>.log` accanto
all'exe. Opzioni: `--quiet` (meno righe), `--log=<file>`, `--timeout=<ms>`, `--cached`
(usa la cache GATT di Windows invece di riscoprire), `--no-session`, `--write-uuid=`,
`--notify-uuid=`, `--register` (invia prima il messaggio fisso di registrazione).

Se qualcosa non funziona, mandami il file `ace_debug_*.log`: contiene tutto il necessario.
Cosa mi aspetto di poter leggere lì:

| Sintomo nel log | Probabile causa |
|---|---|
| `device not found` | cuffie non associate a Windows come LE, oppure fuori portata |
| `service not found` / `status=Unreachable` | cuffie collegate al telefono, oppure già connesse da un'altra app |
| elenco servizi senza `0000fe07-…` | UUID diversi: dal `services` si vedono quelli veri (poi `--write-uuid=`) |
| `characteristics ... not found` | gli UUID di controllo sono diversi: stesso rimedio |
| `AccessDenied` / `ATT-error=0x05` / `0x0F` | serve l'associazione/cifratura: rifai l'associazione in Windows |
| `no reply within ...` ma `write status=Success` | comando inviato, nessuna risposta: provare `--register`, o `sniff` |

## Build locale (facoltativa)

```bat
cmake -S cpp -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
build\ace_tests.exe
```

Il nucleo del protocollo (`core/ace_protocol.hpp`) è C++17 portabile, con test in `tests/`
eseguiti anche su Linux dalla Action. L'app (`app/ace_cli.cpp`) è C++20 per le coroutine di C++/WinRT.
