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
| UUID servizio / caratteristiche | **ignoti** – la discovery GATT è in cache anche in EXP-02 (letto solo il Database Hash `d994c3f9165b746506af2baeaa89c461`); l'advertising riporta solo il nome "Sonos Ace", nessun UUID. Un client Windows può leggerli a runtime (`bleak`: elenco servizi), oppure dall'APK | – | EXP-01, EXP-02 |
| Registrazione client | Write Command su `0x004e`: `01 06 04 00 14 00 00 00 10 51468da4854b7bd88171310705bbebbe`, risposta notify su `0x0050`: `01 07 00 00 02 00 00`. **Identico in EXP-01 ed EXP-02** (16 byte fissi, non un nonce) | P | EXP-01 t≈2.19 s, EXP-02 stessa posizione. Probabile ID dell'app/client: da rinviare così com'è; non è verificato se i comandi su 0x44 lo richiedano |
| Autenticazione applicativa | nessuna visibile sui comandi 0x44 (nessun challenge/risposta variabile) | P | EXP-01, EXP-02 |

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

- Confermata in EXP-02 (secondo log, stessa sequenza `02, 00, 01` con partenza in ANC: trasparenza → off → ANC). Resta fondata sull'ordine dichiarato dall'utente, non su una verifica audio.
- Nessun livello continuo visto (solo 3 valori distinti).
- Ipotesi: `00 04 07` = lettura dello stato corrente della modalità (stessa codifica: 01 = ANC).

### Impostazioni scrivibili (categoria `02`, EXP-02)

Formato: `00 02 <id> <vv>`, risposta `02 02 <id> 00` (ack, nessun eco del valore).
`vv` è un **intero con segno a 8 bit** (complemento a due: `ff` = -1, `f6` = -10).

| id | Funzione | Range osservato | Conf. | Evidenza |
|---|---|---|---|---|
| `0f` | Modalità rumore (`02` trasparenza, `00` off, `01` ANC) | 3 valori | P | EXP-01, EXP-02 |
| `1e` | **Bass** | -10 … +10 | P | EXP-02: 05→0a→(scende)→00→f6→(sale)→04, come il flusso 4 → +10 → -10 → 4 |
| `1f` | **Treble** | -10 … +10 | P | EXP-02: 01→0a→00→f6→00, come 0 → +10 → -10 → 0 |
| `22` | **Bilanciamento** (`+` = destra, `-` = sinistra) | -10 … +10 | P | EXP-02: 02,05,07,08,0a → 00 → fd…f6 → 00, come 0 → tutto dx → tutto sx → 0 |

L'app invia un comando per ogni passo dello slider (≈ 80–150 ms): per un client basta un
singolo comando con il valore finale. Non è stata osservata alcuna lettura del valore
corrente di `1e`/`1f`/`22` (non figurano nella lettura iniziale).

### Lettura iniziale dei parametri (categoria `02`, EXP-01)

All'avvio l'app interroga con `00 02 xx` tutti i parametri della categoria `02`. Valori
letti nella sessione EXP-01 (dopo il byte di stato `00`; le lunghezze/tipi dei valori non
sono ancora decodificati). Servono da **elenco delle funzioni** per EXP-02: gli id non
elencati qui (es. `0f`, la modalità rumore) sono scritti solo dall'interfaccia.

| id | risposta (dopo `02 02 xx`) | note |
|---|---|---|
| `04` | `00 03` | ? (uguale in EXP-01 ed EXP-02, quindi **non** è bass/treble/balance) |
| `09` | `00 09 "Sonos Ace"` | nome dispositivo |
| `0c` | `00 07` | ? |
| `0e` | `00 01` | ? |
| `10` | `00 01` | ? |
| `12` | `00 00` | ? |
| `18` | `02` | ? (risposta senza byte di stato) |
| `1a` | `00 02` | ? |
| `1c` | `00 06 00 01` (EXP-01) → `00 04 00 01` (EXP-02) | ? (cambiato tra le due sessioni) |
| `21` | `00 00` | ? |
| `27` | `00 00` | ? |
| `29` | `05` | ? |
| `2f`, `31`, `33`, `39`, `3b`, `3d` | `02` | ? (stesso formato di `18`) |
| `35`, `37` | `00 01` | ? |

Altre categorie lette all'avvio: `03/03` → `00 41` (EXP-01) / `00 26` (EXP-02): probabile **volume** assoluto 0–127, coerente con le notify `01 03 80 vv` (ipotesi), `03/07` → `00 00`, `01/0c` → `00 01`,
`01/04` → `00 00`, `05/03 <idx>` (tabella a 3 voci), `06/09` → `00 00 00`, `09/03` → `00 00 00`.

**Limite**: dopo la riassociazione serve un log in modalità snoop *Abilitato* (non
*Filtrato*): in "Filtrato" i payload ATT vengono troncati e i valori dei set (EQ, modalità)
spariscono.

### Eventi non richiesti (notify, prefisso `01`)

| Notify | Note |
|---|---|
| `01 04 80 02`, `01 03 80 41`, `01 00 81 02` | burst a t≈88.57 s (cambio di stato non legato a comandi) |
| `01 03 80 3d`, `…39`, `…36`, `…32`, `…2e`, `…2a`, `…26` | sequenza che decresce di ~4 per passo a t≈91–92 s: probabile **volume** o livello (I) |

## Domande aperte

- Valore/comando per "amplificatore suoni" (non ancora catturato).
- "Amplificatore suoni" è un valore di `0f` o un comando diverso?
- Come si legge il valore corrente di bass/treble/balance (nessun getter visto)?
- Funzioni nascoste/non esposte: confrontare con la tabella dei comandi nell'APK.
- Lo stato cambiato dal tasto fisico viene notificato (`01 …`)? Con quale formato?
- UUID di servizio e caratteristiche (per implementare un client senza handle fissi).
- Significato delle categorie `00 00`, `00 01`, `00 05`, `00 06`, `00 09`.
