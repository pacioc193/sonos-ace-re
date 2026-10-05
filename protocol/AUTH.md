# Autorizzazione del canale di controllo (cosa è misurato, cosa no)

Il test da Windows (EXP-03) mostra che si connette il servizio `0xFE07`, si scrivono i
comandi e si ricevono risposte, **ma ogni comando torna con `NO_PERMISSIONS` (9)**. Il client
non è autorizzato. Questo documento distingue nettamente:

- **ciò che è misurato direttamente sulle Sonos Ace** (catture del dispositivo + test Windows);
- **ciò che è dedotto dal codice dell'app**, che è un SDK **condiviso tra più prodotti**
  (cuffie, speaker, home theater). Qui è facile attribuire all'Ace cose che riguardano altri
  prodotti o altri flussi: le affermazioni dedotte sono marcate come tali.

## Misurato sulle Ace (alta confidenza)

1. Il controllo è **GATT/BLE**, servizio `0000FE07`, caratteristiche di controllo
   `…9C9A` (write-without-response) e `…9C9B` (notify). Confermato da catture e da Windows.
2. Senza autorizzazione, **ogni comando ACP riceve `NO_PERMISSIONS` (9)**. La scrittura va a
   buon fine, quindi è un rifiuto applicativo, non un errore Bluetooth.
3. Prima dei comandi, il telefono fa **un solo scambio** sulla caratteristica di setup
   (`…9C9E` → `…9C9F`): write `01 06 04 00 14 00 00 00 10 <16 byte>` e risposta
   `01 07 00 00 02 00 00`. Nessun altro messaggio, nessun nonce sul filo. I 16 byte sono
   **identici in quattro connessioni separate** (EXP-01, EXP-02, EXP-03b, EXP-04) ⇒ valore statico,
   non derivato per sessione né rigenerato a ogni apertura dell'app. Lo scambio avviene
   **una volta per connessione** (tipicamente all'apertura/foreground dell'app) ed è il
   *gate* che precede i comandi: solo dopo la risposta `… 00 00` i comandi ACP tornano
   `SUCCESS` (EXP-03b: 27 risposte con status `00`, zero `NO_PERMISSIONS`). Il byte `10`
   prima del token ne indica la lunghezza (16); il resto dell'header è coerente con
   l'handshake BLEV4 ma non verificato byte-per-byte.
4. Da Windows abbiamo inviato **gli stessi identici byte** e ottenuto `01 07 00 00 02 80 01`
   (diverso: rifiuto) invece di `… 00 00`. Richiesta identica, risposta diversa: l'unica
   variabile è il **peer Bluetooth**. ⇒ l'autorizzazione è **legata all'identità/bond del
   dispositivo** che l'ha stabilita, non al semplice contenuto del messaggio.
   **EXP-06 (riproduzione sul device col token reale):** con `ace.exe --token=<token reale del
   telefono>` e handle↔UUID ormai confermati, l'handshake su `…9C9E` riceve ancora `… 80 01` e il
   primo comando `00 02 0e` (GetAncMode) torna `02 02 0e 09` = `NO_PERMISSIONS`. La catena completa
   (handshake rifiutato → comando negato) è quindi dimostrata con il credenziale vero, non solo con
   il placeholder. (Col telefono *spento* il link LE cade subito dopo la scrittura dell'handshake:
   nessuna risposta — comunque nessuna autorizzazione.)

5. La discovery GATT del telefono è **in cache**: nella riconnessione (EXP-03b) il telefono non
   rienumera servizi/caratteristiche, ma legge solo il *Database Hash* (`0x2B2A`) e le *Server
   Supported Features* (`0x2B3A`); trovando l'hash invariato riusa la mappa già nota. Perciò
   `handle↔UUID` **non** è ricavabile dalle catture del telefono finché la cache resta valida.

Conclusione solida: il controllo delle Sonos Ace è aperto **solo a un peer autorizzato**, e
l'autorizzazione è vincolata al bond/identità Bluetooth. Riproporre i byte catturati da un
altro host non basta.

### Sull'ipotesi "handshake all'apertura dell'app" (EXP-03b)

C'è effettivamente un handshake per-connessione (punto 3), quindi l'intuizione è corretta nella
forma. **Ma non è dinamico**: su quattro connessioni separate il token di 16 byte è bit-per-bit
identico, quindi non viene negoziato/rigenerato all'apertura. L'apertura dell'app riusa lo stesso
segreto statico, già associato durante il pairing. Le due letture compatibili con i dati —
"handshake dinamico che però ridà sempre lo stesso valore a parità di bond" vs "token statico
presentato dal bond" — restano indistinguibili sul filo; in entrambe la barriera pratica è la
stessa (serve essere **quel** telefono). Un eventuale segreto *fresco* potrebbe esistere solo
**fuori banda** (minting lato cloud quando l'app fa login), non visibile in una cattura BLE.
EXP-04: aprire l'app più volte sulla **stessa** connessione LE non ripete l'handshake; serve una
vera disconnessione fra le aperture per osservare handshake separati.

## Dedotto dal codice (confidenza media, da non sopravvalutare)

Tracciando le classi (package `com.sonos.sdk.*`, non offuscato):

- Il percorso di connessione delle cuffie è `bluetooth.connection.HeadphonesBleConnection` →
  `bluetooth.blev4.SonosBlev4Client`. È un **trasporto "BLEV4"** (pacchetti, frame, CRC16,
  handshake, heartbeat). Lo scambio `01 06 … → 01 07 …` del punto 3 è **molto probabilmente
  l'handshake del trasporto BLEV4** (tipi messaggio 06/07 = richiesta/risposta handshake),
  **non** un token di autenticazione cloud. *(dedotto, non confermato byte-per-byte)*
- Sopra il trasporto viaggiano i comandi **ACP** (modalità, EQ, ecc.), con lo stato
  `NO_PERMISSIONS` tra i codici di risposta `ACPResponseStatusValue`.

### Correzione rispetto a una stesura precedente

Una versione precedente di questo file attribuiva all'Ace un sistema di autenticazione
**ASP/ARP/AAP con registrazione cloud e attestazione via certificato del produttore**.
Verificando i riferimenti nel codice, **quelle classi
(`accessory.setup.*`, `AccessoryAuthenticationProtocolClient`, …) sono chiamate solo da
`SetupOperation`**, cioè dal flusso di *setup/onboarding* — che nell'SDK copre anche scenari
di speaker/home theater (LanSwap, TrueRoom, HtPrimaries, household). **Non** risultano chiamate
dal percorso di controllo per-connessione delle cuffie. Quindi la storia "cloud + certificati"
**non è dimostrata per il canale di controllo dell'Ace** ed era un'attribuzione sbagliata:
probabilmente riguarda la registrazione iniziale e/o altri prodotti.

Cosa resta aperto (meccanismo non confermato dell'autorizzazione dell'Ace):
- un'autorizzazione stabilita **una volta** durante l'associazione, legata al bond, che il
  trasporto BLEV4 poi "presenta" a ogni connessione; oppure
- un modello a **token di accesso ACP** (`PRIMARY_ACCESS` / `COMMON_ACCESS` / `ISSUER` esistono
  nell'SDK) legato al dispositivo; oppure
- una **proprietà della connessione** (un solo controller autorizzato per volta).

Per distinguerli servirebbe catturare l'HCI del telefono durante una **nuova associazione**
delle Ace (per vedere come nasce l'autorizzazione) e confrontarla con una riconnessione.

## Conseguenze pratiche (quello che conta davvero)

Indipendentemente dal meccanismo esatto, il fatto misurato è: **lo stesso messaggio da un host
diverso viene rifiutato**. L'autorizzazione è vincolata all'identità Bluetooth del telefono che
l'ha ottenuta. Usarla da un altro dispositivo richiederebbe presentarsi come **quel** telefono
(clonarne il bond BLE / identità) — chiavi protette sul telefono — ed è impersonazione del
dispositivo. Questa è la barriera reale, confermata sperimentalmente.

Resta pienamente valido e verificato tutto ciò che sta **a valle** dell'autorizzazione: il
protocollo di controllo ACP in [NOTES.md](NOTES.md). Manca solo essere un client autorizzato.
