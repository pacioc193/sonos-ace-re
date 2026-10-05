# Autorizzazione del canale di controllo (perché serve, e com'è fatta)

Il test da Windows (EXP-03) ha dimostrato che si può connettere il servizio di controllo
`0xFE07`, scrivere i comandi e ricevere risposte, **ma ogni richiesta torna con
`status=NO_PERMISSIONS` (9)**. Il client non è autorizzato. Questo documento ricostruisce,
dagli identificatori dell'app (package `com.sonos.sdk.accessory.setup`, non offuscato),
**come** l'app diventa autorizzata. Nessun segreto o chiave è incluso qui.

Conclusione in breve (aggiornata con EXP-03b e l'analisi dell'handshake sul filo):
l'autenticazione **per connessione è offline** e consiste in **una sola presentazione di un
token "bearer"** da 16 byte, senza nonce né sfida live. Il cloud Sonos serve **una sola volta**,
alla registrazione, per *coniare* quel token. Il token però è **legato all'identità/bond
Bluetooth del telefono** che l'ha registrato: rimandandone i byte esatti da un altro host le
cuffie rispondono con uno stato di rifiuto. Non è quindi riusabile senza clonare il bond del
telefono (chiavi protette sul telefono).

## Tre sotto-protocolli

### ASP – Accessory Setup Protocol (attestazione del dispositivo)
Handshake iniziale tra app e cuffie. Messaggi `ASPMessageType`:
`CLIENT_HELLO (0)`, `SERVER_HELLO (1/2/3)`, `CLIENT_CHALLENGE (4)`,
`SERVER_RESPONSE (5/6/7)`, `SERVER_STATUS (8)`.
Elementi scambiati (`ASPElementType`): versione, flags, **session id**, **certificato del
produttore** (multipart, `MFG_CERT_DATA`), hash del certificato, dati di modello (MDP:
model/submodel/revision/variant/region), **nonce** e **firma del nonce**
(`NONCE` / `NONCE_SIGNATURE`).
→ Le cuffie provano la propria autenticità firmando un nonce con una chiave legata a un
certificato del produttore; l'app lo valida (`CertificateValidator`, `AttestationResult`).

### ARP – Accessory Registration Protocol (registrazione via cloud)
Messaggi `ARPMessageType`: `CLIENT_ACTIVATE (0)`, `CLIENT_REGISTER (1)`, `CLIENT_RESPONSE (2)`.
Implementato con chiamate HTTP ai server Sonos (classi `RegistrationService`, `RestService`,
`OkHttp*`, `SetupAuthToken`, `OkHttpTokenRefresher`). Endpoint trovati nell'app:
`/product/v2/accessories?action=activate`, `/product/v2/accessories?action=register`,
`/authTokens:generate`, `/auth/o2/token`, OAuth v4.
→ La registrazione produce i **token** che autorizzano il client. Sono rilasciati dal cloud,
non negoziati solo con le cuffie.

### AAP – Accessory Authentication Protocol (autenticazione per connessione)
È il passo che manca al nostro client. **Non contiene nonce** tra i suoi elementi
(il nonce/firma sta in ASP, cioè nell'associazione iniziale, non qui). Messaggi `AAPMessageType`:
`CLIENT_HELLO (0)`, `SERVER_HELLO (1)`, `SELECT_AUTH_METHOD (2/3)`,
`GET_TOKEN (4/5)`, `AUTHENTICATE (6/7)`.
Elementi (`AAPElementType`): `STATUS (0)`, `PROTO_VERSION (1)`, `FLAGS (2)`,
`AUTH_METHOD (3)`, `WRAPPED_TOKEN (4)`.
Tipi di token (`AAPTokenType` / `AuthenticationType`):
`PRIMARY_ACCESS (0)`, `COMMON_ACCESS (1)`, `ISSUER (2)`.
Stati (`AAPStatusCode`): `OK (0)`, `ERROR (8000)`, `INVALID_TOKEN (8001)`.
→ A ogni connessione il client presenta un **wrapped token** (cifrato/firmato) e le cuffie lo
verificano. Un token assente o non valido ⇒ niente permessi.

Crypto presente nell'app a supporto: AES-GCM, HKDF-SHA256/384, HMAC-SHA, firme (RSA/JWT),
`ClientCryptoDelegate`, `ClientEncryptedStorageDelegate` (il token è conservato cifrato).

## Perché i nostri test falliscono (EXP-03)

| Prova | Risultato | Lettura |
|---|---|---|
| Nessuna registrazione | `NO_PERMISSIONS` su ogni comando | manca del tutto l'autenticazione AAP |
| Rimando del messaggio da 25 byte col token del telefono | risposta `01 07 00 00 02 **80 01**` (il telefono otteneva `… 00 00`) | token riconosciuto ma **non valido per questa sessione**: autorizzazione negata |
| Stesso messaggio con token casuale | **disconnessione immediata**, nessuna risposta | token sconosciuto rifiutato: non è un valore arbitrario |

**Handshake reale del telefono sul filo (EXP-03b, identico in entrambe le catture):** un solo
`write` sulla caratteristica di setup (`01 06 04 00 14 00 00 00 10 <token 16 byte>`) e una sola
notifica di risposta (`01 07 00 00 02 00 00`). Nessun altro messaggio, nessun nonce. Il token è
**statico** (gli stessi 16 byte in due connessioni separate), quindi non è derivato per sessione.

Da Windows abbiamo inviato **gli stessi identici byte** e ottenuto `01 07 00 00 02 80 01`
(rifiuto) invece di `… 00 00`. Richiesta identica, risposta diversa: l'unica variabile è il
**peer Bluetooth**. Il token è perciò accettato solo dal dispositivo (bond/identità) che l'ha
registrato. Le stringhe dell'app conciliano: "private key can be used for unwrapping",
`AndroidKeyStore`, `Creating bond with …`.

## Conseguenze per un client indipendente

Il muro **non** è il cloud per connessione (il controllo è offline) né un nonce live. È che il
token da 16 byte, pur statico e in nostro possesso, è **vincolato all'identità Bluetooth del
telefono**. Per usarlo da un altro host servirebbe presentarsi alle cuffie **come quel
telefono**, cioè clonarne il bond BLE (LTK/IRK) o l'identità: chiavi custodite sul telefono
(Keystore, non esportabili senza root) e, di fatto, impersonazione del dispositivo. Minare un
token *nuovo* per un dispositivo nuovo richiede invece la registrazione ARP presso il cloud
Sonos con la crittografia del client. Entrambe le vie restano chiuse per mezzi leciti.

Resta invece pienamente valido e verificato tutto ciò che sta a valle dell'autorizzazione:
il protocollo di controllo ACP (modalità ANC/trasparenza, EQ, balance, ecc.) in
[NOTES.md](NOTES.md). Serve solo che un client sia un client autorizzato.

## Cosa resterebbe da studiare (se si prosegue)

- Il dettaglio di ASP/ARP/AAP è nelle classi `com.sonos.sdk.accessory.setup.*`: strutture dei
  messaggi, ordine, elementi. Documentare il **formato** è RE lecito di interoperabilità.
- Va tenuta separata la differenza tra **documentare** il protocollo e **ottenere**
  un'autorizzazione valida: la seconda dipende dal cloud Sonos e dai segreti del dispositivo,
  e non è un problema di formato ma di credenziali.
