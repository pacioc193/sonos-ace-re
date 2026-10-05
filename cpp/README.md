# ace.exe – client Windows (C++/WinRT)

Console app Win32 che parla con le Sonos Ace via BLE (GATT). Non serve compilare: la
GitHub Action `build` produce l'exe a ogni push e lo pubblica nella Release **latest**
(link diretto: `https://github.com/pacioc193/sonos-ace-re/releases/download/latest/ace.exe`;
il repo è privato, quindi serve essere loggati su GitHub).

Requisiti: Windows 10 1709+ / Windows 11 con Bluetooth LE, cuffie già associate a Windows.
**Spegni il Bluetooth del telefono** (non basta chiudere l'app Sonos) prima di provare: le cuffie
tengono il collegamento di controllo col telefono e il servizio `0xFE07` risulta `Unreachable` da
Windows finché il telefono le occupa. Se la discovery *mirata* fallisce, il client riprova
automaticamente con l'elenco completo e con la cache GATT di Windows (EXP-05); puoi anche forzare
`--cached` per saltare il tentativo lento.

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
`--notify-uuid=`, `--no-register` (salta la registrazione), `--token=<32 hex>|random`
(default: placeholder redatto, non valido).

Se qualcosa non funziona, mandami il file `ace_debug_*.log`: contiene tutto il necessario.
Cosa mi aspetto di poter leggere lì:

| Sintomo nel log | Probabile causa |
|---|---|
| `device not found` | cuffie non associate a Windows come LE, oppure fuori portata |
| `service not found` / `status=Unreachable` | cuffie collegate al telefono, oppure già connesse da un'altra app |
| elenco servizi senza `0000fe07-…` | UUID diversi: dal `services` si vedono quelli veri (poi `--write-uuid=`) |
| `characteristics ... not found` | gli UUID di controllo sono diversi: stesso rimedio |
| `AccessDenied` / `ATT-error=0x05` / `0x0F` | serve l'associazione/cifratura: rifai l'associazione in Windows |
| `status=NO_PERMISSIONS` su ogni risposta | client non registrato: vedi *Registrazione* sotto |
| `no reply within ...` ma `write status=Success` | comando inviato, nessuna risposta: provare `sniff` |

## Build locale offline (senza scaricare l'exe)

Servono il sorgente (GitHub: *Code → Download ZIP*, oppure `git clone`), un **compilatore
MSVC** (Visual Studio o Build Tools con il carico di lavoro *Sviluppo di applicazioni desktop
con C++*; il solo Windows SDK non contiene il compilatore) e un Windows SDK 10.0.17134 o più
recente (per le intestazioni C++/WinRT). Poi, da un prompt qualsiasi:

```bat
cpp\build.bat
build\ace.exe help
```

Con Visual Studio 2017 usa `/std:c++17 /await`, con 2019 o più recente `/std:c++20` (scelta automatica). Lo script trova da solo Visual Studio con `vswhere`, imposta l'ambiente, compila i test del
protocollo (e li esegue) e poi `ace.exe`, tutto in `cpp\build\`. Per scegliere un SDK preciso:
`set WINSDK=10.0.26100.0` prima di lanciarlo. Nessuna connessione di rete è necessaria.

## Build con CMake (alternativa)

```bat
cmake -S cpp -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
build\ace_tests.exe
```

Il nucleo del protocollo (`core/ace_protocol.hpp`) è C++17 portabile, con test in `tests/`
eseguiti anche su Linux dalla Action. L'app (`app/ace_cli.cpp`) è C++20 per le coroutine di C++/WinRT.

## Registrazione

Il primo test (Windows 11, 2026-10-05) ha confermato UUID e canali, ma le cuffie rispondevano
`NO_PERMISSIONS` a ogni richiesta. Il telefono, prima del primo comando, scrive un messaggio
fisso da 25 byte sulla caratteristica *setup* (`…9C9E`) e riceve la risposta su `…9C9F`.
`ace.exe` ora fa lo stesso passaggio per default, prima di abilitare le notifiche di controllo.
Cerca nel log `registration reply:` e poi lo stato dei comandi. Varianti da provare, in ordine:

```bat
ace.exe auto probe                    :: placeholder redatto (default): dara' NO_PERMISSIONS
ace.exe auto probe --token=<32 hex>   :: il token reale visto nelle tue catture
ace.exe auto probe --token=random     :: un token nuovo: se funziona, non serve quello del telefono
ace.exe auto probe --no-register      :: per confronto
```
