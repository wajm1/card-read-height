# rf IDEAS — Credential Read Height Automation

Automated credential read height testing using a **UFACTORY Lite 6** robot arm and rf IDEAS WAVE ID readers.

## Folder layout

```
Automation/
├── config.py              # Shared settings and card map
├── run.py                 # Launch GUI
├── requirements.txt
│
├── gui/                   # Application UI
│   ├── app.py             # Main window
│   └── checks.py          # Startup hardware checks
│
├── hwg/                   # HWG+ reader configuration files
│   └── cepas.hwg+
│
├── robot/                 # Lite 6 motion and test runner
│   ├── controller.py      # Robot SDK stub — implement here
│   └── test_runner.py     # Test sequence entry point
│
├── reader/                # Reader tools
│   ├── cli.py             # RRMTool CLI helpers (used by GUI)
│   ├── ReaderConfig.py    # CLI config tool
│   └── ReaderConfigSDK.py # USB HID config tool
│
├── barcode/               # Barcode scanner
│   └── scanner.py         # Scan capture + card lookup
│
└── logs/
    └── results/           # Exported CSV files
```

## Setup

```bash
pip install -r requirements.txt
```

Edit `config.py` for `RRM_CLI`, `ROBOT_IP`, and `CARD_TYPE_MAP`.

## Run

```bash
python run.py
```

Or:

```bash
python gui/app.py
```

## Reader CLI tools

```bash
python reader/ReaderConfig.py about
python reader/ReaderConfig.py load [file.hwg+]
python reader/ReaderConfigSDK.py about
```

## Next steps

1. Implement `robot/controller.py` with the Lite 6 Python SDK
2. Wire `robot/test_runner.py` to robot motion + read detection
3. Add HWG files to `hwg/` and barcodes to `CARD_TYPE_MAP` in `config.py`

---

Internal use only — rf IDEAS
