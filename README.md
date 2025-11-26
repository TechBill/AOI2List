# AOI2List – USGS LiDAR AOI Tile Finder & LAZ Downloader

**Developer:** Bill Fleming (TechBill)
**Contact:** `billyjackrootbeer (at sign) gmail (dot) com`
**Donations:** https://www.paypal.com/paypalme/techbill

AOI2List is a Python tool for locating and downloading USGS LiDAR LAZ tiles
from ScienceBase using a simple Area-Of-Interest (AOI) defined by latitude,
longitude, and square miles.

There are two components:

- `aoi2list.py` — Command-line tool for generating a text list of LAZ URLs
- `aoi2list_gui.py` — Graphical interface (Tkinter) for selecting and downloading tiles

---

## Features

- AOI defined as a square area centered on given coordinates
- Queries USGS ScienceBase for matching LiDAR tiles
- Tile metadata: tile ID, bounding box, flight date
- GUI includes:
  - Tile selection checkboxes
  - Save URL list to a `.txt` file
  - Direct LAZ downloads with progress bar, speed display, retry logic, and cancel button
- CLI generates a simple URL list suitable for batch downloading

---

## Installation

### 1. Install Python 3.8+
Windows and macOS users can download Python from:
https://www.python.org/downloads/

### 2. Install Python dependencies

```bash
python -m pip install -r requirements.txt
```

`requirements.txt` contains:

```
requests>=2.0
```

Tkinter is included automatically with Python on Windows/macOS.

---

## Command-line Usage (aoi2list.py)

Example:

```bash
python aoi2list.py --lat 37.1 --lon -92.6 --sqmi 6 --out downloadlist.txt
```

Arguments:

| Flag     | Description                                    |
|----------|------------------------------------------------|
| --lat    | Center latitude (decimal)                      |
| --lon    | Center longitude (decimal)                     |
| --sqmi   | Square miles of AOI (must be > 0)              |
| --out    | Output text file for URLs (default: downloadlist.txt) |

---

## GUI Usage (aoi2list_gui.py)

Run:

```bash
python aoi2list_gui.py
```

Steps:

1. Enter **latitude**, **longitude**, **sq miles**
2. Click **Find Tiles**
3. A tile selection window opens:
   - Check/uncheck tiles
   - Save selected URLs to a `.txt`
   - Or download selected `.laz` files

During download:

- Percent complete
- MB downloaded
- Speed (MB/s)
- Cancel button
- Automatic retry on failures

---

## Building Standalone Apps with PyInstaller

First install PyInstaller:

```bash
python -m pip install pyinstaller
```

### Windows

```bash
pyinstaller --noconfirm --onefile --windowed aoi2list_gui.py
```

### macOS

```bash
pyinstaller --noconfirm --onefile --windowed aoi2list_gui.py
```

Optional custom name and icon:

```bash
pyinstaller --noconfirm --onefile --windowed   --name AOI2List   --icon aoi2list.icns   aoi2list_gui.py
```

---

## License

This project uses a **custom non-commercial software license**.

- Free for personal, research, and educational use
- Modification and redistribution allowed **with attribution**
- **Commercial use requires permission** from the developer

See the full text in the included **LICENSE** file.

---

## Support / Contact

Questions, feedback, or bug reports:
`billyjackrootbeer (at sign) gmail (dot) com`

If this tool saves you time, donations are appreciated:
https://www.paypal.com/paypalme/techbill
