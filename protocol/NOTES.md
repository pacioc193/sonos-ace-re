# Protocollo Sonos Ace – note

Regola: ogni affermazione ha un livello di confidenza e un riferimento all'evidenza.
Confidenza: **C** confermato (riprodotto / inviato con successo), **P** probabile
(coerente tra catture e identificatori dell'app), **I** ipotesi.

Fonti: **EXP-01/EXP-02** = catture HCI ([../captures/EXPERIMENTS.md](../captures/EXPERIMENTS.md));
**APK** = nomi e valori numerici degli identificatori nell'app Sonos 89.01.11 (solo
identificatori di protocollo, nessun codice riprodotto qui).

> **Autorizzazione:** il canale di controllo richiede un client autenticato. Senza
> autenticazione ogni comando riceve `NO_PERMISSIONS`. Vedi [AUTH.md](AUTH.md).

## Trasporto: GATT su BLE

| Voce | Valore | Conf. | Evidenza |
|---|---|---|---|
| Servizio | `0000FE07-0000-1000-8000-00805F9B34FB` | P | APK (costante del servizio Sonos) |
| `accessory_control`: scrittura / notifica | `C44F42B1-F5CF-479B-B515-9F1BB0099C9A` / `…9C9B` | P | APK; nelle catture handle `0x0044` (Write Command) / `0x0046` (Notification) |
| `accessory_data` | `…9C9C` / `…9C9D` | P | APK (non visto nelle catture) |
| `accessory_setup` (priorità alta) | `…9C9E` / `…9C9F` | I | APK; il messaggio fisso su handle `0x004e`/`0x0050` potrebbe essere questo canale |
| `accessory_true_room_microphone` | `…9CA5` / `…9CA6` | P | APK |
| Servizio batteria standard | `0000180F` / `00002A19` | P | APK |
| Qualcomm GAIA (v3, upgrade) | `00001100-D102-11E1-9B23-00025B00A5A5`, `…1101`, `…1102`, `…1103` | P | APK (usato dall'app per l'aggiornamento firmware) |
| CCCD | `00002902`, scritto `0100` per abilitare le notifiche | C | EXP-01/02 |
| MTU | richiesta 512 | C | EXP-01/02 |
| Corrispondenza handle ↔ UUID | **non verificata** (discovery GATT in cache nelle catture) | – | confermare con `ace.py services` |

Il messaggio fisso su `0x004e` (identico in EXP-01 ed EXP-02):
`01 06 04 00 14 00 00 00 10 51468da4854b7bd88171310705bbebbe`, risposta notify su `0x0050`:
`01 07 00 00 02 00 00`. L'app contiene anche un'handshake "BLEv4" con CRC16: il legame
con questo messaggio non è verificato. Nessuna autenticazione visibile sui comandi di controllo.

## Framing: ACP (Accessory Control Protocol)

Messaggio (host → cuffie su scrittura, cuffie → host su notifica):

```
byte 0   tipo        00 = richiesta, 02 = risposta, 01 = evento non richiesto
byte 1   gruppo      vedi tabella gruppi
byte 2   PDU id      per gli eventi >= 128 (0x80)
byte 3.. risposta: stato (1 byte) + dati; richiesta: parametri
```

Nessun campo lunghezza, checksum o contatore sui messaggi di controllo osservati.
Stringhe: lunghezza (1 byte) + ASCII. Valori numerici con segno: complemento a due (`ff` = -1).

**Stato risposta** (APK): `0` SUCCESS, `1` NAMESPACE_NOT_SUPPORTED, `2` COMMAND_NOT_SUPPORTED,
`3` INSUFFICIENT_RESOURCES, `4` INVALID_PARAMETER, `5` INVALID_STATE, `6` INVALID_HEADER,
`7` INVALID_LENGTH, `8` UNEXPECTED_ERROR, `9` NO_PERMISSIONS.

### Gruppi (secondo byte)

| Gruppo | Nome (APK) | Conf. | Evidenza |
|---|---|---|---|
| `00` | Status (`GetInfo`=3 → versione firmware, `GetChargingState`=4, `GetCurrentActivity`=5, `GetBatteryHealth`=6, `GetMoistureDetectState`=7, `GetPlaybackTimeRemaining`=8, `GetMtu`=9, `GetFeatureCount`=10, `GetFeatureInfo`=11) | P | `00 00 03` → firmware `3.9.9-…` |
| `01` | Management (opt-in 4/5, `GetHtPrimaries`=6, multipoint 11/12, dispositivi associati 25, pairing 21/26…) | P | EXP-01/02 |
| `02` | **Settings** (tabella sotto) | C | EXP-01/02 |
| `03` | Volume (`GetVolume`=3, `SetVolume`=4, `Mute`=5, `Unmute`=6, `GetMuteState`=7, prompt volume 8/9) | P | `00 03 03` → volume; evento `01 03 80 vv` |
| `04` | Playback (`Play`=3, `Pause`=4, `SkipBack`=5, `SkipToNextTrack`=6, `GetPlaybackStatus`=7) | P | `00 04 07` → `00 01`; evento `01 04 80 vv` |
| `05` | PlaybackMetadata (`GetMetadataStatus`=3, parametro = indice campo) | I | `00 05 03 <idx>` |
| `06` | SoundSwap | I | `00 06 09` = `GetSwapState` |
| `09` | TrueRoom (`GetCalibrationState`=3, start/stop calibrazione/mic) | I | `00 09 03` |

Gruppi 05, 06, 09 dedotti dagli id osservati: da verificare. AudioShare non osservato.

## Impostazioni (gruppo `02`)

Ogni impostazione ha un PDU `Get` (risposta: stato + valore) e uno `Set` (parametro = valore;
risposta: solo stato, `02 02 <id> 00`).

### Confermate da catture (C/P)

| Funzione | Set | Get | Valori |
|---|---|---|---|
| **Modalità rumore** | `0f` (15) | `0e` (14) | `00` off, `01` ANC, `02` trasparenza. EXP-01/02; `GetAncMode` all'avvio = `01` con le cuffie in ANC |
| **Bass** | `1e` (30) | in `GetCustomEq` | int8, -10…+10 |
| **Treble** | `1f` (31) | in `GetCustomEq` | int8, -10…+10 |
| **Loudness** | `20` (32) | in `GetCustomEq` | 0/1 (non provato; all'avvio = 1) |
| **Bilanciamento** | `22` (34) | `21` (33) | int8 -10…+10, + = destra |
| **EQ personalizzato** | – | `1c` (28) | risposta `00 <bass> <treble> <loudness>`; all'avvio EXP-02: bass 4, treble 0, loudness 1 |
| Nome | `0a` (10) | `09` (9) | stringa (`Sonos Ace`) |

### Presenti sulle cuffie (letture all'avvio EXP-02) ma non ancora comandate

| Funzione | Get → risposta all'avvio | Note |
|---|---|---|
| `GetAdaptiveAncMode` (55) | OK, `01` | modalità ANC adattiva (set = 56) |
| `GetSelfVoiceAnc` (53) | OK, `01` | gestione della propria voce in ANC (set = 54) |
| `GetAncButtonCustomization` (4) | OK, `03` | quali modalità cicla il pulsante (set = 6) |
| `GetWearDetectionActions` (12) | OK, `07` | azioni al rilevamento indossamento (set = 13) |
| `GetSpatialAudioMode` (16) | OK, `01` | set = 17 |
| `GetHeadTrackingMode` (18) | OK, `00` | set = 19 |
| `GetDolbyHeadTrackingMode` (39) | OK, `00` | set = 40 |
| `GetAutoOffTimer` (26) | OK, `02` | set = 27 |
| `GetSnoozeTimer` (41) | INVALID_STATE | set = 42 |

### Non supportate da queste cuffie (COMMAND_NOT_SUPPORTED)

`GetLowPowerMode` (24), `GetAllowFastCharging` (51), `GetAncSpeakToChatMode` (49), `GetVoiceBoostMode` (47),
vocal guidance: enable (57), battery readout (59), language (61).

### Elenco completo dei PDU del gruppo Settings (APK)

| id | hex | nome |
|---|---|---|
| 4 | `0x04` | GetAncButtonCustomization |
| 6 | `0x06` | SetAncButtonCustomization |
| 9 | `0x09` | GetName |
| 10 | `0x0a` | SetName |
| 11 | `0x0b` | ResetName |
| 12 | `0x0c` | GetWearDetectionActions |
| 13 | `0x0d` | SetWearDetectionActions |
| 14 | `0x0e` | GetAncMode |
| 15 | `0x0f` | SetAncMode |
| 16 | `0x10` | GetSpatialAudioMode |
| 17 | `0x11` | SetSpatialAudioMode |
| 18 | `0x12` | GetHeadTrackingMode |
| 19 | `0x13` | SetHeadTrackingMode |
| 24 | `0x18` | GetLowPowerMode |
| 25 | `0x19` | SetLowPowerMode |
| 26 | `0x1a` | GetAutoOffTimer |
| 27 | `0x1b` | SetAutoOffTimer |
| 28 | `0x1c` | GetCustomEq |
| 29 | `0x1d` | ResetCustomEq |
| 30 | `0x1e` | SetBass |
| 31 | `0x1f` | SetTreble |
| 32 | `0x20` | SetLoudness |
| 33 | `0x21` | GetBalance |
| 34 | `0x22` | SetBalance |
| 35 | `0x23` | GetDaxSupport |
| 36 | `0x24` | SetDaxSupport |
| 39 | `0x27` | GetDolbyHeadTrackingMode |
| 40 | `0x28` | SetDolbyHeadTrackingMode |
| 41 | `0x29` | GetSnoozeTimer |
| 42 | `0x2a` | SetSnoozeTimer |
| 43 | `0x2b` | GetLedColorblindMode |
| 44 | `0x2c` | SetLedColorblindMode |
| 45 | `0x2d` | GetContentKeyPressSpeed |
| 46 | `0x2e` | SetContentKeyPressSpeed |
| 47 | `0x2f` | GetVoiceBoostMode |
| 48 | `0x30` | SetVoiceBoostMode |
| 49 | `0x31` | GetAncSpeakToChatMode |
| 50 | `0x32` | SetAncSpeakToChatMode |
| 51 | `0x33` | GetAllowFastCharging |
| 52 | `0x34` | SetAllowFastCharging |
| 53 | `0x35` | GetSelfVoiceAnc |
| 54 | `0x36` | SetSelfVoiceAnc |
| 55 | `0x37` | GetAdaptiveAncMode |
| 56 | `0x38` | SetAdaptiveAncMode |
| 57 | `0x39` | GetVocalGuidanceEnable |
| 58 | `0x3a` | SetVocalGuidanceEnable |
| 59 | `0x3b` | GetVocalGuidanceBatteryReadout |
| 60 | `0x3c` | SetVocalGuidanceBatteryReadout |
| 61 | `0x3d` | GetVocalGuidanceLanguage |
| 62 | `0x3e` | SetVocalGuidanceLanguage |
| 63 | `0x3f` | GetEqSettings |
| 64 | `0x40` | SetActiveEqType |
| 65 | `0x41` | SetEqSliderPosns |
| 66 | `0x42` | ResetEqSettings |
| 67 | `0x43` | GetLoudness |
| 68 | `0x44` | SetAdaptiveEQMode |
| 69 | `0x45` | GetAdaptiveEQMode |
| 128 | `0x80` | AncModeStatusEvent |
| 129 | `0x81` | SpatialAudioSettingChangeEvent |
| 130 | `0x82` | LowPowerModeEvent |
| 131 | `0x83` | DolbyHeadTrackingChangeEvent |

PDU id ≥ 128 sono eventi inviati dalle cuffie: `AncModeStatusEvent` (128), `LowPowerModeEvent`
(130), `SpatialAudioSettingChangeEvent` (129), `DolbyHeadTrackingChangeEvent` (131).
Non supportati o non ancora provati: LED colorblind mode (43/44), content key press speed
(45/46), DAX support (35/36), adaptive EQ (68/69), EQ slider positions (65), active EQ type
(64), reset EQ (66) e reset nome (11).

## Correzioni rispetto a note precedenti

- `00 04 07` **non** legge lo stato ANC: è `GetPlaybackStatus` (gruppo Playback). Lo stato ANC
  si legge con `00 02 0e`.
- `02/04` è `GetAncButtonCustomization`, non bass.
- `03/03` = volume (non ipotesi): `GetVolume`.

## Domande aperte

- Handle ↔ UUID (confermare con `ace.py services`) e ruolo del messaggio su `0x4e`.
- Valori di `SetAdaptiveAncMode`, `SetSelfVoiceAnc`, `SetLoudness`, modalità audio spaziale e timer di spegnimento.
- Livelli intermedi per trasparenza/ANC: nessuno trovato nei comandi `0f`; verificare `AdaptiveAncMode`.
- Il codice dei pulsanti fisici e le notifiche di cambio modalità da tasto (`AncModeStatusEvent` = `01 02 80 vv`, da verificare).

## EXP-03 – Primo test da Windows 11 (C++/WinRT, 2026-10-05)

- **Confermato su un dispositivo reale (C):** servizio `0000FE07-…`, caratteristiche di controllo
  `…9C9A` (write-without-response) e `…9C9B` (notify); scrittura riuscita, risposte ricevute con
  latenza ≈ 90 ms. Le cuffie compaiono a Windows come LE con lo stesso indirizzo del collegamento classico.
- **Senza registrazione ogni richiesta riceve `status=NO_PERMISSIONS` (9)** (probe di 13 richieste:
  `02 <gruppo> <pdu> 09`). Il decoder dei messaggi è quindi giusto: è un rifiuto a livello di protocollo.
- Ipotesi (I): serve il passaggio di registrazione sul canale *setup* (`…9C9E`/`…9C9F`, handle `0x4e`/`0x50`
  nelle catture), con un token da 16 byte. Da verificare con `ace.exe auto probe` (registra per default).
