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

_(nessun esperimento ancora eseguito)_
