# Analisi statica dell'app Sonos (supporto)

Serve a dare nomi e struttura a ciò che si vede nelle catture. **Nessun file
prodotto qui (APK, output jadx, snippet decompilati) va committato** – lavorare
in `work/`, che è ignorata da git.

## 1. Ottenere l'APK

```sh
adb shell pm path com.sonos.acr2          # verificare il package name reale
adb pull <path>/base.apk work/sonos.apk   # più eventuali split_*.apk
```

## 2. Decompilazione

```sh
jadx -d work/jadx work/sonos.apk
```

Se il codice di controllo è in una libreria nativa (`lib/arm64-v8a/*.so`), usare
Ghidra; se è un'app React Native / Flutter, cercare il bundle JS / `libapp.so`.

## 3. Cosa cercare

```sh
cd work/jadx
grep -rniE 'anc|noise.?cancel|aware|transparen|ambient' --include=*.java | less
grep -rnE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' --include=*.java | sort -u
grep -rnE 'createRfcommSocket|listenUsingRfcomm|connectGatt|writeCharacteristic|setCharacteristicNotification' --include=*.java
grep -rniE 'protobuf|GeneratedMessage|\.proto' --include=*.java | head
```

Indizi utili:
- UUID custom → servizio GATT o record SDP del canale di controllo
- enum / costanti con nomi tipo `NOISE_CONTROL`, `ANC_MODE`, `AWARE_LEVEL`
- classi che serializzano messaggi (protobuf, TLV, header fissi) → framing
- CRC / checksum calcolati prima della scrittura

## 4. Hook dinamico con Frida (opzionale)

Permette di vedere i messaggi **prima** della serializzazione o della cifratura
eventuale. Richiede root o un APK ripacchettato con frida-gadget.

```js
// work/hook.js
Java.perform(() => {
  const G = Java.use('android.bluetooth.BluetoothGatt');
  G.writeCharacteristic.overload('android.bluetooth.BluetoothGattCharacteristic', '[B', 'int')
    .implementation = function (c, v, t) {
      console.log('GATT W', c.getUuid(), bytesToHex(v));
      return this.writeCharacteristic(c, v, t);
    };
  const OS = Java.use('java.io.OutputStream');  // RFCOMM socket stream
  OS.write.overload('[B').implementation = function (b) {
    console.log('OS W', this.$className, bytesToHex(b));
    return this.write(b);
  };
  function bytesToHex(b) {
    return Array.from(b, x => ('0' + (x & 0xff).toString(16)).slice(-2)).join('');
  }
});
```

```sh
frida -U -f com.sonos.acr2 -l work/hook.js
```

Riportare in [../protocol/NOTES.md](../protocol/NOTES.md) solo le **conclusioni**
(UUID, formato, significato dei campi), non il codice decompilato.
