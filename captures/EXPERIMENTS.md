# Registro esperimenti

I file di cattura **non** vanno nel repo (`.gitignore`). Qui si annota solo cosa è
stato fatto, quando e cosa si è osservato. Nome file consigliato:
`YYYYMMDD-<id>-<descrizione>.log`, conservato fuori dal repo (es. Google Drive).

## Template

```
### EXP-NN – <titolo>
- Data/ora: 
- Firmware cuffie / versione app: 
- File: 
- Precondizioni: (stato iniziale ANC/Aware, app aperta da quanto, ecc.)
- Azioni (con orari):
  1. hh:mm:ss – 
- Osservazioni: (canale, payload rilevanti, timestamp nel log)
- Conclusioni → protocol/NOTES.md:
```

## Esperimenti pianificati

| ID | Esperimento | Scopo | Stato |
|---|---|---|---|
| EXP-01 | Baseline: BT on, connessione, apertura app, nessuna azione per 60 s | Handshake, discovery, polling/keepalive da filtrare come rumore | ⏳ |
| EXP-02 | ANC on → off → on (3 ripetizioni, 5 s tra ognuna) | Isolare il comando ANC e la risposta | ⏳ |
| EXP-03 | Aware on → off → on (3 ripetizioni) | Isolare il comando Aware | ⏳ |
| EXP-04 | Sweep dei livelli di trasparenza/ANC, se l'app li espone (min → max a passi) | Campo "livello" e codifica | ⏳ |
| EXP-05 | Cambio modalità dal tasto fisico sulle cuffie, app aperta | Notifica di stato rx | ⏳ |
| EXP-06 | Altre impostazioni (EQ, rilevamento indossamento, ecc.), una alla volta | Struttura generale di comando e ID funzione | ⏳ |
| EXP-07 | Riavvio app con modalità già cambiata | Lettura stato iniziale | ⏳ |

## Risultati

### EXP-01 – Primo log: connessione + 3 cicli di modalità (2026-10-05)
- Dispositivo: Pixel 10 Pro, snoop HCI attivo, bugreport del 2026-10-05 10:39.
- File: `btsnoop_hci.log` (398 588 byte, fuori dal repo – su Drive dell'utente).
- Azioni: partenza in cancellazione attiva, poi 3 cicli trasparenza → off → cancellazione
  attiva (ordine confermato dall'utente); orari esatti non annotati.
- Osservazioni: 9 comandi `00 02 0f vv` con vv = 02,00,01,02,00,01,02,00,01, ciascuno
  con ack `02 02 0f 00`. Handshake/lettura iniziale con comandi `00 <cat> <id>` e
  risposte `02 <cat> <id> …` su handle ATT 0x0044/0x0046. Nel log compaiono anche
  Pixel Watch e un terzo dispositivo, da ignorare.
- Conclusioni → [protocol/NOTES.md](../protocol/NOTES.md): trasporto GATT/BLE, comando
  modalità `00 02 0f vv`. Mappatura dedotta: 02 = trasparenza, 00 = off, 01 = ANC.
- Prossimo: EXP-02 con ordine annotato (vedi sotto).

### EXP-02 – Associazione + modalità, EQ e bilanciamento (2026-10-05)
- File: `btsnoop_hci.log` (424 158 byte, fuori dal repo – su Drive dell'utente), snoop in modalità *Attivato*.
- Flusso: associazione; modalità isolamento → trasparenza → off; bass 4 → 10 → -10 → 4;
  treble 0 → 10 → -10 → 0; bilanciamento 0 → tutto dx → tutto sx → 0.
- Osservazioni: 136 comandi su `0x44` con ack su `0x46`. Modalità: `0f` = 02, 00, 01. Bass `1e`,
  treble `1f`, balance `22`: int8 -10…+10, un comando per passo di slider. Handshake `0x4e`
  identico a EXP-01. Discovery GATT ancora in cache: UUID non ottenuti.
- Conclusioni → [protocol/NOTES.md](../protocol/NOTES.md).
- Cause del log filtrato in precedenza: snoop non riavviato dopo il cambio di modalità.

### (superato) Prossimo esperimento dopo EXP-01
Una sola azione per volta, in questo ordine, con 10 s di pausa e annotando l'ordine:
1. ANC **on** → 2. Trasparenza (Aware) → 3. ANC off → 4. "Amplificatore suoni" on.
Ripetere 2 volte. Se possibile, prima del test: dimenticare le cuffie e riassociarle
per catturare anche la discovery GATT (UUID).
