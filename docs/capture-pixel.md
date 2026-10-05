# Cattura HCI snoop su Pixel 10 Pro

Obiettivo: registrare tutto il traffico Bluetooth tra telefono e Sonos Ace mentre
si cambia **una sola** impostazione alla volta nell'app Sonos.

## 1. Abilitare il log

1. Impostazioni → Info sul telefono → tocca 7 volte *Numero build* (Opzioni sviluppatore).
2. Impostazioni → Sistema → Opzioni sviluppatore →
   **Abilita log di snoop HCI Bluetooth** → **Attivato** (non *Filtrato*: il filtrato
   tronca i payload, che sono proprio ciò che serve).
3. Spegni e riaccendi il Bluetooth: il log riparte da zero e include connessione,
   SDP e apertura dei canali (fondamentale per capire PSM / canale RFCOMM / handle GATT).

## 2. Protocollo di un esperimento

- Cuffie già associate, app Sonos chiusa.
- Ciclo BT off/on → accendi le cuffie → apri l'app → aspetta che si stabilizzi (~10 s).
- Esegui **un'azione**, attendi ~5 s, annota l'ora esatta (aiuta a trovarla nel log).
- Ripeti la stessa azione 2-3 volte con pause: ciò che si ripete è il comando.
- Registra tutto in [../captures/EXPERIMENTS.md](../captures/EXPERIMENTS.md).

Una cattura per esperimento: estrarre il log dopo ogni prova (o fare BT off/on tra
un esperimento e l'altro) rende il diff molto più semplice.

## 3. Estrarre il log

Il file vive in `/data/misc/bluetooth/logs/` (non leggibile senza root). Strada
standard senza root:

```sh
adb bugreport bugreport.zip
unzip bugreport.zip 'FS/data/misc/bluetooth/logs/*'
# -> FS/data/misc/bluetooth/logs/btsnoop_hci.log (+ eventuale .last)
```

Senza PC: Opzioni sviluppatore → *Segnala un bug* → *Report interattivo*, poi
condividi lo zip (es. su Google Drive) e caricalo nella sessione di analisi.

> Il log contiene indirizzi BT e chiavi di link: **non committarlo** (è già in `.gitignore`).

## 4. Prima analisi

```sh
python3 tools/btsnoop_extract.py btsnoop_hci.log | less
```

In Wireshark (`File → Open`), filtri utili:

| Filtro | A cosa serve |
|---|---|
| `btsdp` | servizi pubblicizzati (UUID, canali RFCOMM) |
| `btl2cap.cmd_code == 0x02` | apertura canali L2CAP (PSM) |
| `btrfcomm && btrfcomm.len > 0` | dati applicativi su RFCOMM |
| `btatt` | GATT (LE o BR/EDR) |
| `btatt.opcode == 0x52 \|\| btatt.opcode == 0x12` | scritture verso le cuffie |
| `btatt.opcode == 0x1b` | notifiche dalle cuffie |
| `bthci_evt.code == 0x3e` | connessioni LE |

Cosa cercare per primo:

1. **Trasporto**: le cuffie parlano con l'app via RFCOMM (SPP / UUID custom in SDP) o
   via GATT? Spesso coesistono: GATT per discovery/setup, RFCOMM per il controllo.
2. **Framing**: header fisso? campo lunghezza? contatore di sequenza? checksum?
3. **Comando vs stato**: dopo una scrittura c'è un ack o una notifica di stato?
