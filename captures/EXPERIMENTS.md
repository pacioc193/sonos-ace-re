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
- Log filtrato del tentativo precedente: causa probabile (non verificata) = Bluetooth non riavviato dopo il cambio di modalità snoop.

### EXP-03b – Nuova connessione dal telefono: handshake all'apertura app (2026-10-05)
- Ipotesi di partenza (utente): "all'apertura dell'app Sonos c'è un handshake".
- File: `btsnoop_hci.log` (260 340 byte, fuori dal repo – su Drive dell'utente), cattura dal
  Pixel 10 Pro, terza connessione del telefono alle Ace (stesso bond di EXP-01/02).
- Flusso osservato (solo ATT/BLE; l'RFCOMM nel log è traffico **Pixel Watch / Wear OS**, da ignorare):
  1. `tx 0x51 = 0100` abilita le notifiche sul CCCD del canale *setup*.
  2. `tx 0x4e` **handshake**: `01 06 04 00 14 00 00 00 10 <16 byte>` (il byte `10` = lunghezza 16 del token).
  3. `rx 0x50` risposta `01 07 00 00 02 00 00` → status `00 00` (**OK**).
  4. `tx 0x41` / `tx 0x47 = 0100` abilitano i CCCD del canale di controllo.
  5. `tx 0x44` comandi ACP, ack su `0x46`: **27× status `00` (SUCCESS)**, 10× `02` (COMMAND_NOT_SUPPORTED),
     2× `05` (INVALID_STATE), **0× `09` (NO_PERMISSIONS)**.
- Confronto token: i **16 byte dell'handshake sono identici** in EXP-01, EXP-02 ed EXP-03b (tre
  connessioni separate) ⇒ **valore statico**, non rigenerato per sessione/apertura.
- GATT in cache: il telefono **non** rifà la discovery; legge solo il *Database Hash* (char `0x2B2A`,
  handle `0x0008` sull'Ace = `d994c3f9165b746506af2baeaa89c461`) e le *Server Supported Features*
  (`0x2B3A`). Hash invariato ⇒ cache valida ⇒ **handle↔UUID ancora non ottenibili** da questo log.
  Le letture `read_req/read_rsp` su handle alti (132, 63, 106…) sono l'**Ace che legge dal telefono**
  (il telefono fa da GATT server: ora/Fast Pair/…), non il contrario.
- Conclusioni → [protocol/AUTH.md](../protocol/AUTH.md) e [protocol/NOTES.md](../protocol/NOTES.md):
  l'handshake all'apertura **esiste ed è il gate** del controllo, ma presenta un token **statico**
  legato al bond; confermato il rifiuto cross-host (stessi byte da Windows → `80 01`).
- Prossimo per handle↔UUID: cattura durante un **re-pairing** (svuota la cache GATT) oppure discovery
  live dal nostro client (`ace.py services`).

### EXP-04 – Toggle Bluetooth + app aperta più volte (2026-10-05)
- Ipotesi: più aperture dell'app → più handshake; i 16 byte cambiano?
- File: `btsnoop_hci.log` (303 701 byte, fuori dal repo – su Drive dell'utente), Pixel 10 Pro.
- Osservazioni:
  - **Un solo** handshake su `0x4e` (`tx`), **un solo** CCCD setup abilitato, **una sola raffica**
    di 39 comandi su `0x44`: le riaperture dell'app hanno **riusato la stessa connessione LE**,
    quindi l'handshake non si è ripetuto.
  - Token dei 16 byte **ancora identico** (4ª cattura: EXP-01/02/03b/04) ⇒ statico.
  - La **cache GATT è ancora valida**: solo riletture di `0x2B2A` (DB hash), `0x2B3A` (features) e
    `0x2A04`; nessuna rienumerazione. **Il toggle del Bluetooth NON svuota la cache GATT.**
  - Nel log compare anche un secondo indirizzo (`80:4A:F2:05:AF:27`), da ignorare.
- Conclusioni: conferma "handshake = gate, una volta per connessione, token statico". Per vedere
  **più handshake** serve una vera disconnessione tra le aperture (spegnere/riaccendere le cuffie,
  o *Forza arresto* dell'app Sonos → riapri). Per `handle↔UUID` serve un **re-pairing**
  (Dimentica + riassocia svuota la cache) **oppure** la discovery dal PC (`ace.exe auto services`).

### EXP-05 – Discovery GATT live da Windows (ace.exe C++/WinRT) (2026-10-05)
- Obiettivo: ottenere `handle↔UUID` senza toccare la cache del telefono.
- Setup: Ace associate a Windows 11 (build 26100), `ace.exe auto get anc --token=<reale>`.
- Esito discovery (**confermato**): enumerati 8 servizi; servizio controllo `0xFE07` @ decl `0x0042`:
  `…9C9A`@`0x43`[wNR], `…9C9B`@`0x45`[notify], `…9C9C`@`0x48`[wNR], `…9C9D`@`0x4a`[notify],
  `…9C9E`@`0x4d`[wNR], `…9C9F`@`0x4f`[notify], `…9CA3`@`0x52`[notify], `…9CA4`@`0x55`[read],
  `…9CA5`@`0x57`[wNR], `…9CA6`@`0x59`[notify]. Windows riporta l'handle di **dichiarazione**; il
  **value = +1** combacia con i write/notify delle catture del telefono (`0x44/0x46`, `0x4e/0x50`).
  Altri servizi: GATT `0x1801` (DB hash `0x2B2A`@`0x07`, features `0x2B3A`@`0x09`), GAP `0x1800`,
  GAIA `0x1100`, Fast Pair `0xFE2C`, Qualcomm `0xEB10`/`0xFD92`, Battery `0x180F`.
- Problema aperto (link): la query *mirata* `GetGattServicesForUuid(FE07, Uncached)` torna
  **`Unreachable`** (~7,7 s di timeout) anche se l'elenco completo (cache di Windows) mostra `0xFE07`;
  al 2° tentativo il link cade (`Connected → Disconnected`), `maxPdu=23` (MTU non rinegoziata).
  Sintomo tipico di cuffie ancora tenute dal telefono o di link LE instabile.
- Azioni: (client) discovery resa robusta — se la query mirata fallisce si usa il servizio
  dall'elenco completo, con fallback alla cache GATT; idem per le caratteristiche. (utente) spegnere
  il **Bluetooth del telefono** (non solo chiudere l'app) e rilanciare; eventualmente `--cached`.
- Da verificare al prossimo giro: con il telefono spento, se l'handshake su `…9C9E` riceve
  `… 00 00` (accettato) o `… 80 01` (rifiutato) con `--token=<reale>`.

### EXP-06 – Prova definitiva dell'auth: token reale rifiutato da Windows (2026-10-05)
- Setup: `ace.exe` (build con discovery robusta), Ace associate a Windows, `--token=<token reale
  catturato dal telefono>`.
- **Telefono acceso** — l'intera catena arriva fino in fondo e il rifiuto è netto:
  - handshake su `…9C9E`: `TX 01 06 04 00 14 00 00 00 10 <token reale>` → `RX 01 07 00 00 02 80 01`
    (**rifiutato**, status `0x8001`; il telefono riceve `… 00 00`).
  - comando `00 02 0e` (GetAncMode) → `02 02 0e 09` = **NO_PERMISSIONS**.
- **Telefono spento** — dopo la scrittura dell'handshake il link LE **cade** (`Disconnected`), nessuna
  risposta entro 3 s; riconnette ma anche il comando resta senza risposta. Nessuna autorizzazione.
- **Conclusione (definitiva):** gli **stessi identici byte** del token, inviati da Windows, sono
  rifiutati (`0x8001`) e i comandi tornano `NO_PERMISSIONS`. Riproduce sul dispositivo, con il token
  vero, ciò che era in [AUTH.md](../protocol/AUTH.md): **l'autorizzazione è legata al bond/identità
  BLE del telefono**, non al contenuto del messaggio. Il token da solo non basta da un altro host.
- Vie rimaste: (a) presentarsi come quel bond (clonare chiavi/identità BLE del telefono — protette
  sul telefono, non fattibile); (b) **registrare il PC come nuovo peer autorizzato** — richiede
  catturare l'associazione (re-pairing) per capire come nasce il token legato all'identità del PC.

### EXP-07 – RE di protocollo dalle catture: origine della chiave (2026-10-05)
Analisi delle 4 catture per rispondere a "come/quando l'app ottiene il token da 16 byte".
- **Il token non è mai ricevuto in-band.** In tutte e 4 le catture i 16 byte (`51468da4…`) compaiono
  **una sola volta e solo come `tx`** (scrittura sul canale setup `…9C9E`): mai letti da una
  caratteristica, mai ricevuti dalle cuffie. ⇒ l'app li ha **già memorizzati**, non li ottiene
  durante la connessione né durante le associazioni catturate.
- **Token identico anche nell'associazione (EXP-02).** Quindi non viene rigenerato a ogni pairing:
  è stabile per (dispositivo, account) e preesiste alle catture.
- **Nuovo canale: AAP su RFCOMM (classic BT), DLCI 44**, presente **solo in EXP-02** (la cattura con
  l'associazione). Non è HFP (DLCI 20 = comandi AT). Framing `<gruppo> <pdu> <len16> <payload>`,
  con un namespace `0x07` che porta un **challenge-response a blocchi da 16 byte**:
  `07 41 .."in-use".. <16B>`, `07 40 00 <16B>` + `07 42 00 <16B>`, risposta `07 34 ..`, ack `ff ..`.
  I blob da 16 byte **cambiano a ogni round** → nonce/challenge **per-sessione**, non una chiave fissa.
  (Interpretazione: probabile ARP/AAP del codice; struttura osservata, semantica da confermare.)
- **L'unico rx di 16 byte su BLE** (handle `0x1d`) è **Google Fast Pair** (char `fe2c1234`), non il token.
- **Conclusione (P):** il token BLE statico non nasce da uno scambio BLE riproducibile; coerente con un
  **provisioning fuori banda** (cloud Sonos legato all'account) al primissimo setup, poi salvato
  nell'app. Per *vederlo* nascere serve una cattura del **primo setup dopo factory reset** +
  **traffico di rete (HTTPS)** del telefono, non solo l'HCI snoop.

### (superato) Prossimo esperimento dopo EXP-01
Una sola azione per volta, in questo ordine, con 10 s di pausa e annotando l'ordine:
1. ANC **on** → 2. Trasparenza (Aware) → 3. ANC off → 4. "Amplificatore suoni" on.
Ripetere 2 volte. Se possibile, prima del test: dimenticare le cuffie e riassociarle
per catturare anche la discovery GATT (UUID).
