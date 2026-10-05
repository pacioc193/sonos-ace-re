# client

`ace.py` – client BLE (GATT) in Python con [bleak](https://github.com/hbldh/bleak),
per Windows 10/11, Linux e macOS. Implementa modalità, bass, treble e balance secondo
[../protocol/NOTES.md](../protocol/NOTES.md). **Non ancora provato sulle cuffie**: i
comandi sono verificati solo byte per byte contro le catture (`tests/test_ace.py`).

```sh
pip install bleak
python3 client/ace.py scan                        # trova "Sonos Ace" e l'indirizzo
python3 client/ace.py services <addr>             # elenco servizi/caratteristiche (UUID)
python3 client/ace.py <addr> mode anc|aware|off
python3 client/ace.py <addr> bass|treble|balance -10..10   # balance: + destra, - sinistra
python3 client/ace.py <addr> raw 00020f01         # comando arbitrario, stampa la risposta
```

Gli UUID non sono ancora noti: senza `--write-uuid`/`--notify-uuid` il client prova a
riconoscere il servizio personalizzato con una caratteristica *write-without-response* e
una *notify*. Se non funziona, lancia `services` e passa gli UUID a mano.

**Handshake (default).** Prima dei comandi il client esegue l'handshake sul canale di
setup come fa il telefono (EXP-03b): abilita la notify, scrive `01 06 04 00 14 00 00 00 10
<16 byte token>` e classifica la risposta (`… 00 00` = accettato, `… 80 01` = rifiutato).
Senza un token valido usa un placeholder: i comandi torneranno `NO_PERMISSIONS`. Passa il
tuo con `--token <32 cifre hex>`. Disattiva lo step con `--no-register`. Il token è una
credenziale legata al bond del telefono (vedi [../protocol/AUTH.md](../protocol/AUTH.md)):
riproporlo da un altro host viene rifiutato. Chiudi l'app Sonos sul telefono prima di provare.
