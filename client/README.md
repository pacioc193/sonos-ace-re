# client

Placeholder. Il client verrà scritto dopo aver identificato trasporto e comandi
(vedi [../protocol/NOTES.md](../protocol/NOTES.md)):

- **GATT** → Python + [bleak](https://github.com/hbldh/bleak)
- **RFCOMM** → Python `socket.AF_BLUETOOTH` / `BTPROTO_RFCOMM` (Linux) o app Android minimale

Interfaccia prevista:

```sh
python3 client/ace.py <bdaddr> anc on|off
python3 client/ace.py <bdaddr> aware on|off [--level N]
python3 client/ace.py <bdaddr> status
```
