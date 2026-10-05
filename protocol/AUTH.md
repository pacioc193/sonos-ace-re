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

6. Il telefono usa **indirizzi BLE privati risolvibili (RPA)**, diversi a ogni connessione
   (misurato, EXP-09): `45:12:71…`, `71:1e:61…`, `6b:a8:4e…`, `6d:bf:1b…` (primi due bit `01`).
   Non esiste quindi un MAC fisso da copiare: l'Ace riconosce il telefono **risolvendo l'RPA con
   l'IRK** scambiato al pairing. ⇒ l'identità del peer è ancorata alle **chiavi del bond (IRK/LTK)**,
   non all'indirizzo. Spoofare il MAC non basta: generare un RPA che l'Ace risolve al telefono
   richiede **l'IRK del telefono**.

## Come l'Ace valida il token (meccanismo)

Il token da 16 byte **da solo non autorizza**: EXP-06 mostra gli **stessi byte** rifiutati da un
altro peer (`80 01`). L'Ace non fa "token giusto → ok", ma **"questo token appartiene al peer che me
lo manda?"**. Poiché la verifica è **locale** (le cuffie non hanno internet) e il telefono usa RPA,
la catena coerente con tutte le misure è:

1. il peer si connette con un RPA → l'Ace lo **risolve con l'IRK** del bond → è il controller X;
2. il link è sul **bond** del pairing (IRK/LTK) → prova d'identità;
3. il token presentato deve **corrispondere** a quello registrato per X.

Windows fallisce ai passi 1–2 (bond diverso, chiavi proprie) → l'Ace lo vede come peer diverso/non
registrato e il token del telefono non è legato a quell'identità → `80 01`. **In sintesi: non valida
"il token", valida "sei il peer a cui quel token è legato"**, con l'identità ancorata alle chiavi del
pairing. *(Confidenza: alta sul fatto che il legame sia all'identità/bond — misurato; media sul
dettaglio dei passi. Se l'Ace faccia un confronto di uguaglianza per-identità o una verifica
crittografica — es. HMAC — e il ruolo esatto del challenge-response AAP/DLCI 44, lo direbbe solo il
RE del firmware dell'Ace, che non abbiamo.)*

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

### Il token è nell'APK? Da dove arriva? (EXP-07)

**No, non come costante compilata.** EXP-06 mostra che gli stessi byte da un peer diverso sono
rifiutati: il valore è legato a *questo* telefono/associazione, quindi **non può** essere un literal
di build (sarebbe uguale per tutti gli utenti e autorizzerebbe qualunque Ace). Quando l'app
costruisce la scrittura `01 06 … <16B>`, il token **non** proviene da una stringa dell'APK ma è
**letto a runtime dallo storage locale** (SharedPreferences/DB/Android Keystore), dove è stato
salvato al primo setup.

Evidenza dalle catture (EXP-07): i 16 byte compaiono **solo come scrittura in uscita**, mai ricevuti
via radio, e sono **identici anche nella cattura dell'associazione** → preesistono e non vengono
rigenerati al pairing.

**Correzione importante (EXP-08, ragionamento): la validazione è LOCALE sull'Ace, non sul cloud.**
Le Ace non hanno un percorso internet durante la sessione e nelle catture **accettano il token
completamente offline** (EXP-01/02). Quindi il controllo del token lo fa **l'Ace stessa**, in locale,
contro l'identità/bond BLE del peer — il cloud non può essere nel percorso di verifica in tempo reale.
Ne segue che il token è un **segreto condiviso localmente** (Ace ↔ controller), stabilito al
**primissimo pairing** e poi solo *ripresentato*. Lo scambio **AAP su RFCOMM DLCI 44** (challenge-
response a 16 byte, EXP-07) è il candidato per quel key-establishment locale. La precedente ipotesi
"provisioning cloud" va ridimensionata: il cloud/account, se interviene, può al più **sbloccare/avviare**
il primo setup nell'app, ma **non valida** le connessioni successive. Questo **riapre la fattibilità** di
un client autonomo: se la registrazione è locale, un client che rifà il primo bond può ottenere un
**proprio** token ed essere autorizzato offline.

**Test decisivo (EXP-08, da fare):** factory reset delle Ace → telefono in **modalità aereo** (niente
Wi-Fi/dati) → tentare il **primo setup** nell'app Sonos.
- setup completato offline e controllo funzionante ⇒ token **locale**, nessun cloud necessario ⇒ client autonomo fattibile;
- app che rifiuta senza internet ⇒ il cloud fa da **gate** alla sola registrazione.
In parallelo resta utile la cattura del primo setup (HCI snoop; + HTTPS solo se il telefono è online).

**Piano di RE statico mirato** (sull'APK, solo identificatori/struttura — niente codice nel repo):
- cercare *dove si costruisce* la scrittura `01 06 04 00 14 00 00 00 10` (prefisso del setup) o il
  valore della caratteristica `…9C9E`: la classe che assembla quel buffer rivela da quale campo
  prende i 16 byte;
- seguire a ritroso quel campo: è letto da **storage locale** (prefs/DB/Keystore) o da una **risposta
  di rete** (registrazione ARP/cloud)? Il nome della chiave/DAO lo dice;
- classi candidate: `SetupOperation`, `AccessoryAuthenticationProtocolClient` / ARP / ASP,
  `bluetooth.blev4.SonosBlev4Client`, e il canale **AAP su RFCOMM** (DLCI 44, namespace `0x07`,
  EXP-07) con PDU `0x40/0x41/0x42` a blocchi da 16 byte;
- stringhe utili da grepare: `in-use`, `token`, `accessKey`/`access_key`, `PRIMARY_ACCESS`,
  `COMMON_ACCESS`, `ISSUER`, `household`, `register`, `credential`.

**Attenzione (vale anche se lo troviamo):** localizzare o estrarre il token **non** abilita il
controllo dal PC, perché l'autorizzazione è legata all'**identità BLE** del telefono (EXP-06). La
strada utile che il RE deve chiarire non è "trovare il token", ma **come si registra un nuovo
controller** (così il PC diventa un peer autorizzato con un proprio token).

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
