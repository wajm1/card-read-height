# Credential Read Height Automation

Automated credential **read-height testing** for rf IDEAS WAVE ID readers using a
**UFACTORY Lite 6** robot arm, a USB barcode scanner, and rf IDEAS reader-config tooling.

The robot picks a card from a stack, scans its barcode to identify the card type,
configures the reader for that type, then lowers the card toward the reader until a
read is detected — recording the read height for each card.

## Repository layout

```
card-read-height/
├── README.md            ← you are here (overview)
├── .gitignore
│
├── Automation/          ← all application code (run scripts from here)
│   ├── config.py            Central settings: reader, robot IP, test params, card map
│   ├── requirements.txt     Python dependencies
│   ├── README.md            Quick reference
│   ├── barcode/             Barcode scanner capture + card lookup
│   ├── gui/                 Tkinter control/monitoring GUI
│   ├── logs/                Runtime logs (git-ignored)
│   ├── reader/              Reader configuration tools (RRMTool CLI + USB HID SDK)
│   └── robot/               Lite 6 motion + the read-height test runner
│
├── docs/                ← full documentation (start with docs/SETUP.md)
│
├── files/               ← AllCards.csv + hwg/*.hwg+ (read at runtime)
│
└── results/             ← test-output CSVs (git-ignored)
    └── Keep/                Curated results to retain in version control
```

> **Paths matter:** `config.py` treats the folder *above* `Automation/` as the
> workspace root, so `files/` and `results/` must stay at the top level. Don't move them.

## Quick start

```bash
cd Automation
pip install -r requirements.txt

# Launch the GUI
python gui/gui.py

# …or run the test from the command line
python robot/cardreadheight.py --cycles 14
```

See **[docs/SETUP.md](docs/SETUP.md)** for installation and configuration,
**[docs/USAGE.md](docs/USAGE.md)** for how to run tests, **[docs/API.md](docs/API.md)**
for the module reference, and **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** when
something breaks.

---

Internal use only — rf IDEAS
