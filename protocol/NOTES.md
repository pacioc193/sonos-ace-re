# Protocollo Sonos Ace – note

Regola: ogni affermazione ha un livello di confidenza e un riferimento all'evidenza
(ID esperimento in [../captures/EXPERIMENTS.md](../captures/EXPERIMENTS.md), timestamp,
offset). Confidenza: **C** confermato (riprodotto / inviato con successo),
**P** probabile (visto più volte), **I** ipotesi.

Tutti i timestamp sono in secondi relativi al primo record ATT dell'handle LE nel log.

## Trasporto

| Voce | Valore | Conf. | Evidenza |
|---|---|---|---|
| Canale di controllo | **GATT su BLE** (non RFCOMM) | P | EXP-01: tutto il traffico di controllo è ATT su un collegamento LE; sul link BR/EDR della stessa periferica c'è solo HFP (AT) |
| Scrittura comandi | attribute handle `0x0044`, **Write Command** (0x52, senza risposta ATT) | C | EXP-01 |
| Risposte / eventi | attribute handle `0x0046`, **Notification** (0x1B) | C | EXP-01 |
| CCCD abilitati | scritti `0100` su più handle subito dopo la connessione (0x41, 0x47, 0x45, 0x48, 0x51, ...) | P | EXP-01 t≈0.4–2.4 s |
| MTU | richiesta 512 (0x0200), risposta 512 | C | EXP-01 t=0 |
| UUID servizio / caratteristiche | **ignoti** – la discovery GATT era già in cache (l'host ha solo letto il Database Hash) | – | serve nuova cattura con cuffie dimenticate e riassociate |
| Servizio secondario | scrittura 17 byte `01 06 04 00 14 00 00 00 10 <16 byte casuali>` su `0x004e`, risposta notify `01 07 00 00 02 00 00` su `0x0050` | I | EXP-01 t≈2.19 s: sembra un handshake / scambio di nonce, ma i comandi su 0x44 funzionano subito dopo |
| Autenticazione applicativa | nessuna visibile sui comandi 0x44 | I | |

## Framing (provvisorio)

Comando (host → cuffie, handle `0x0044`):

```
offset  len  campo
0       1    00          costante nei comandi osservati (direzione/tipo = "richiesta")
1       1    categoria   (vedi tabella)
2       1    id comando
3..     n    parametri (opzionali; 1 byte per i set osservati)
```

Risposta (cuffie → host, handle `0x0046`):

```
0       1    02          "risposta" (richiesta 00 -> risposta 02)
1       1    categoria   (eco)
2       1    id comando  (eco)
3..     n    dati; spesso 00 = ok, poi eventuale lunghezza + valore
```

Eventi non richiesti iniziano con `01` (vedi sotto). Nessun campo lunghezza globale,
checksum o contatore di sequenza osservato nei comandi 0x44.

## Comandi osservati (categoria / id)

| Comando (hex) | Risposta (hex) | Significato probabile | Conf. |
|---|---|---|---|
| `00 00 03` | `02 00 03 00 0f "3.9.9-01c2510 22…"` + dati | versione firmware (stringa ASCII) | P |
| `00 00 0a` | `02 00 0a 02` | ? | |
| `00 00 04` / `05` | `02 00 04 00 00` / `02 00 05 00 00` | ? | |
| `00 00 08` / `06` / `07` | `02 00 08 02` / `02 00 06 02` / `02 00 07 05` | ? | |
| `00 02 09` | `02 02 09 00 09 "Sonos Ace"` | **nome del dispositivo** | C |
| `00 01 06` | `02 01 06 00 01 0c "542A1BDDA708"` | stringa 12 caratteri esadecimali (ID/seriale/MAC?) | I |
| `00 06 04` | `02 06 04 00 0c "824AF205AF27"` | stringa 12 caratteri: sembra l'indirizzo BT della periferica | I |
| `00 05 03 00/01/02` | `02 05 03 00 <idx> 00 00 …` (idx 2 → vuoto; idx 0 → "Not Provided") | tabella indicizzata (slot / dispositivi associati?) | I |
| **`00 02 0f <v>`** | **`02 02 0f 00`** (ack, uguale per ogni v) | **modalità di controllo del rumore** | P (vedi sotto) |

### Controllo rumore: `00 02 0f vv`

Osservato in EXP-01: 9 comandi consecutivi, intervallo ≈ 1.2–1.7 s, valori
`02, 00, 01, 02, 00, 01, 02, 00, 01`. Ogni comando riceve l'ack `02 02 0f 00`
(stato 00 = ok, senza eco del valore).

Ordine delle azioni dichiarato dall'utente: partenza in cancellazione attiva, poi tre
cicli **trasparenza → off → cancellazione attiva**.

| vv | Modalità | Conf. | Evidenza |
|---|---|---|---|
| `02` | Trasparenza (Aware) | P | 1º comando di ogni ciclo |
| `00` | Off | P | 2º comando di ogni ciclo |
| `01` | Cancellazione attiva (ANC) | P | 3º comando di ogni ciclo; coerente con la lettura iniziale `00 04 07` → `02 04 07 00 01` (stato ANC all'avvio) |

- Mappatura dedotta dall'ordine, non da tre esperimenti separati: conferma definitiva con EXP-02.
- Nessun livello continuo visto (solo 3 valori distinti).
- Ipotesi: `00 04 07` = lettura dello stato corrente della modalità (stessa codifica: 01 = ANC).

### Eventi non richiesti (notify, prefisso `01`)

| Notify | Note |
|---|---|
| `01 04 80 02`, `01 03 80 41`, `01 00 81 02` | burst a t≈88.57 s (cambio di stato non legato a comandi) |
| `01 03 80 3d`, `…39`, `…36`, `…32`, `…2e`, `…2a`, `…26` | sequenza che decresce di ~4 per passo a t≈91–92 s: probabile **volume** o livello (I) |

## Domande aperte

- Conferma della mappatura 02/00/01 con esperimenti separati, e valore per "amplificatore suoni".
- "Amplificatore suoni" è un valore di `0f` o un comando diverso?
- Esistono parametri di livello per Aware (campo aggiuntivo) o è solo on/off?
- Lo stato cambiato dal tasto fisico viene notificato (`01 …`)? Con quale formato?
- UUID di servizio e caratteristiche (per implementare un client senza handle fissi).
- Significato delle categorie `00 00`, `00 01`, `00 05`, `00 06`, `00 09`.
