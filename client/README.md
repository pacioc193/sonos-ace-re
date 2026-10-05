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
una *notify*. Se non funziona, lancia `services` e passa gli UUID a mano. Prima del
primo comando potrebbe servire `--register --register-uuid <uuid>` (messaggio fisso
visto nelle catture). Chiudi l'app Sonos sul telefono prima di provare.
