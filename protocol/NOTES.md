# Protocollo Sonos Ace – note

Regola: ogni affermazione ha un livello di confidenza e un riferimento all'evidenza
(ID esperimento in [../captures/EXPERIMENTS.md](../captures/EXPERIMENTS.md), timestamp,
offset). Confidenza: **C** confermato (riprodotto / inviato con successo),
**P** probabile (visto più volte), **I** ipotesi.

## Trasporto

| Voce | Valore | Conf. | Evidenza |
|---|---|---|---|
| Bluetooth classico / LE / entrambi | ? | | |
| Canale di controllo (RFCOMM ch / PSM / servizio GATT) | ? | | |
| UUID servizio / record SDP | ? | | |
| Caratteristica di scrittura | ? | | |
| Caratteristica di notifica | ? | | |
| Pairing / bonding richiesto | ? | | |
| Autenticazione a livello applicativo | ? | | |

## Framing

```
offset  len  campo         note
0       ?    ?
```

- Endianness: ?
- Campo lunghezza (copre cosa?): ?
- Sequenza / ID transazione: ?
- Checksum / CRC (algoritmo, copertura): ?
- Cifratura applicativa: ?

## Comandi

| Funzione | Direzione | Payload (hex) | Risposta attesa | Conf. | Evidenza |
|---|---|---|---|---|---|
| ANC on | tx | | | | |
| ANC off | tx | | | | |
| Aware on | tx | | | | |
| Aware off | tx | | | | |
| Livello trasparenza N | tx | | | | |
| Lettura stato corrente | tx | | | | |
| Notifica cambio da tasto fisico | rx | | | | |

## Domande aperte

- Esistono livelli intermedi di trasparenza nel protocollo o solo on/off?
- Lo stato viene notificato quando si cambia modalità dal tasto sulle cuffie?
- Serve un handshake/sessione prima che i comandi siano accettati?
