# sonos-ace-re

Reverse engineering del protocollo Bluetooth di controllo delle cuffie **Sonos Ace**,
con l'obiettivo di comandare da un client indipendente (Linux / Android / ESP32)
le modalità di cancellazione del rumore: **ANC on/off**, **Aware (trasparenza)** e,
se esposti dal protocollo, i **livelli intermedi**.

Al momento non risultano progetti pubblici che documentino questo protocollo.

## Stato

| Fase | Stato |
|---|---|
| Scaffold, tool di estrazione | ✅ |
| Cattura HCI snoop da Pixel 10 Pro | ⏳ da fare |
| Trasporto: GATT/BLE, servizio 0xFE07 | ✅ |
| Protocollo comandi ACP (ANC, EQ, balance, ...) | ✅ |
| Client PoC (Python + C++/WinRT) | ✅ comandi, ⛔ bloccato dall'auth |
| Autorizzazione (ASP/ARP/AAP, cloud) | 🔒 barriera crittografica, vedi [protocol/AUTH.md](protocol/AUTH.md) |

## Approccio

1. **Analisi dinamica** – catture `btsnoop_hci.log` dal telefono mentre l'app Sonos
   cambia un'impostazione alla volta → [docs/capture-pixel.md](docs/capture-pixel.md)
2. **Estrazione e diff** – `tools/btsnoop_extract.py` isola i payload ATT/RFCOMM,
   `tools/diff_hex.py` evidenzia i byte che cambiano tra esperimenti
3. **Analisi statica** (supporto) – decompilazione dell'app per trovare UUID,
   canali e struttura dei messaggi → [docs/static-analysis.md](docs/static-analysis.md)
4. **Documentazione** – ogni scoperta va in [protocol/NOTES.md](protocol/NOTES.md)
   con l'evidenza (cattura + offset) che la supporta
5. **Client** – implementazione minimale in `client/`

## Layout

```
tools/        script Python (solo stdlib)
  btsnoop_extract.py   btsnoop H4 -> payload ATT/RFCOMM (testo o JSONL)
  diff_hex.py          diff byte-a-byte di payload o di un file JSONL
tests/        test unitari con log sintetici
docs/         procedure di cattura e analisi statica
protocol/     specifica ricostruita del protocollo
captures/     registro esperimenti (i log grezzi NON vanno committati)
client/       client PoC (dopo aver capito il protocollo)
```

## Uso rapido

```sh
python3 tools/btsnoop_extract.py btsnoop_hci.log                  # tutto, testo
python3 tools/btsnoop_extract.py btsnoop_hci.log --proto rfcomm   # solo RFCOMM UIH
python3 tools/btsnoop_extract.py btsnoop_hci.log --jsonl > exp.jsonl
python3 tools/diff_hex.py --jsonl exp.jsonl --dir tx              # cosa cambia nei comandi inviati
python3 tools/diff_hex.py 0a0102ff 0a0103ff                       # confronto manuale
python3 -m unittest discover -s tests                             # test
```

## Nota legale

Progetto di interoperabilità a scopo personale/di ricerca sul proprio dispositivo.
Il repository **non contiene** e non deve contenere APK, firmware, codice decompilato
o altro materiale protetto di Sonos: solo osservazioni del protocollo, strumenti
scritti da zero e documentazione originale. Le catture grezze restano fuori dal repo
(contengono indirizzi BT e chiavi di link). Sonos e Sonos Ace sono marchi dei rispettivi
proprietari; questo progetto non è affiliato né approvato da Sonos.

## Licenza

[MIT](LICENSE)
