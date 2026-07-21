# QSL Manager

[🇪🇸 Español](README.md) | 🇬🇧 English

Local (Windows) app to organize ham radio QSL cards: import images or
PDFs, automatically recognize the data (callsign, country, date, band,
mode, locator), and browse them in a gallery, map, and slideshow -- with
filters by country and mode, direct import from eQSL.cc, and either local
recognition (no internet) or AI-based recognition (more accurate).

Everything runs 100% on your PC. The only things that reach the internet
are: map tiles (OpenStreetMap), calls to Gemini if you enable AI,
downloads from eQSL.cc if you use that, and the optional usage-stats ping
(you can turn it off).

## 1. Installation

**Got the `QSLManager.exe` file?** Double-click it and you're done -- no
need to install Python, `pip`, or anything else in this section. The
`.exe` already bundles everything it needs (Python, the libraries,
Tesseract). Skip ahead to **2. First launch**.

**Running it from source instead of the `.exe`?** (for example on
Linux/Mac, or because you're modifying the code) -- then you'll need:

1. **Python 3.10 or newer** — https://www.python.org/downloads/
   When installing, check "Add Python to PATH".
2. In a terminal (PowerShell), inside the project folder:
   ```
   pip install -r requirements.txt
   ```
3. Run:
   ```
   python app.py
   ```

A native window opens with the app. If PyWebview can't open the window
(for example on a server with no graphical environment), the program
prints a URL (`http://127.0.0.1:8756`) to open manually in a browser.

**⚠️ About Tesseract if running from source**: the app works with local
recognition out of the box *only if* the `tesseract-bin/` folder exists
inside the project (included if you got the full code outside of
GitHub). **If you cloned the repo from GitHub, that folder is NOT
there** -- it's excluded on purpose, since it's ~90 MB of third-party
binaries (see `.gitignore`). In that case, for local recognition to
work, you need to install Tesseract yourself:

1. Download it from https://github.com/UB-Mannheim/tesseract/wiki
   (Windows installer, default options)
2. In the app, ⚙ Settings → "Tesseract path" field → paste the full
   path to `tesseract.exe` (usually
   `C:\Program Files\Tesseract-OCR\tesseract.exe`)

Without this step, local recognition (Tesseract) will fail with "not in
your PATH" until you set the path. AI recognition (Gemini, section 4)
doesn't depend on this -- it works fine without Tesseract installed.

## 2. First launch

The first time, a wizard opens asking for:
1. **Language** (Español / English) -- can also be changed later from
   Settings.
2. **Your callsign** -- needed so recognition can tell your station apart
   from the sender of the QSL. It also shows up in the header, handy when
   sharing screenshots.
3. **Enable AI (optional)** -- see section 4.

You can see this wizard again anytime from Settings → "See the welcome
guide again".

## 3. Basic usage

- **+ Import QSLs**: pick one or several images/PDFs. You can also
  **drag and drop** files straight onto the window.
- Every imported card is marked **"Review recognition"** (orange) until
  you open it, confirm or fix the fields, and hit **"Save changes"** --
  that's when it becomes verified. If recognition failed completely, the
  badge shows in red ("Recognition error") with the reason underneath,
  and you can retry with the "↻ Local recognition" or "↻ AI recognition"
  buttons inside the card.
- **🔁 Review pending**: retries recognition on every card that's still
  unverified in one go (for example, if you imported several before
  setting up AI). Runs in the background, you can keep using the app
  meanwhile.
- **Filters**: by country, by mode (FT8, SSB, PSK, RTTY, etc.), and a
  callsign search box with a clear button.
- **Sort**: by date (newest/oldest first) or grouped by country (with
  section headers).
- **Views**:
  - **Gallery**: the normal card view.
  - **Map**: places every QSL with a known location (prioritizes the
    locator/grid square; falls back to country otherwise). Map style
    selector (Voyager, light Positron, dark Dark Matter, classic OSM)
    available there and in Settings.
  - **Slideshow**: shows QSLs one at a time, large, for presenting.
    Auto-advance (seconds configurable, 4 by default) or manual with the
    buttons / arrow keys / spacebar to pause. Respects active filters.
- **Theme**: light, dark, or match system (Settings).
- **Language**: Español / English, with flags, switches instantly
  (welcome wizard or Settings).

## 4. Recognition engine: Tesseract (local) or AI (Gemini)

By default the app uses **Tesseract** (bundled, no internet, always
free). For cards with logos/decorative fonts -- which Tesseract reads
poorly -- you can enable **Google Gemini** (a vision model), which
understands the whole card design. Generous free tier, **no credit card
required**.

1. Go to https://aistudio.google.com/apikey with your Google account
2. Click "Create API key" and then "Create Key"
3. In the app, ⚙ **Settings** → paste the key
4. Click **"Detect"** next to Model -- this asks Google live which models
   are currently available (avoids depending on a fixed name Google can
   retire without notice, which has already happened more than once)
5. Engine set to "Automatic" and Save

With "Automatic": uses Gemini if a key is configured, otherwise falls
back to Tesseract. You can also force a specific engine (globally in
Settings, or per-card with the buttons inside the card detail).

**Pace with AI**: Gemini's free tier limits requests per minute. The app
automatically waits ~4.5s between calls -- a batch of 30 files with AI
enabled takes 2-3 minutes, that's normal.

**Common issues:**
- *Tesseract "not in your PATH"*: paste the full path to `tesseract.exe`
  in Settings (usually not needed, since it's bundled in
  `tesseract-bin/`).
- *Tesseract "[WinError 5] Access denied"*: Windows antivirus interfering
  with temp files. The app already uses its own folder (`data/tmp/`) to
  avoid this; if it persists, add an antivirus exception for the project
  folder.
- *Gemini fails from the very first request*: almost always a model
  Google retired. Use "Detect" in Settings.

## 5. Import from eQSL.cc

**📥 eQSL** button in the header: asks for your eQSL.cc callsign and
password, and pulls your inbox directly -- callsign, date, band and mode
already come confirmed by eQSL, so those cards are marked verified
without going through recognition.

eQSL doesn't allow fast downloads: it pulls **one card every ~2 seconds**,
so a large inbox can take several minutes. Runs in the background (you
can close the modal and keep using the app; a green pill in the header
shows progress from any view). You can **stop and resume** anytime -- it
won't re-download what you already have (a unique ID is stored per
card).

Username and password are saved locally so you don't have to retype them
each time ("💾 Save and close" button if you just want to save them
without downloading yet).

## 6. Usage stats (optional)

Enabled by default, can be turned off in Settings. If active, every time
the app is opened or settings saved with a callsign configured, a ping is
sent (just the callsign, nothing else -- no QSLs or any other data) to a
spreadsheet of the developer's, just to get a sense of how many people
use the app. The endpoint is fixed in the code
(`TELEMETRY_ENDPOINT` in `qsl_manager/server.py`), not something the user
configures.

## 7. Where data is stored

- `data/qsl.db` -- SQLite database with all the metadata.
- `data/cards/` -- a copy of every imported image/PDF (the original file
  stays untouched wherever it was).
- `data/config.json` -- settings (callsign, API key, eQSL credentials,
  preferences). All local, never pushed to any repository.

To back everything up, just copy the `data/` folder.

## 8. Extending country recognition

`qsl_manager/prefixes.json` is a simple dictionary
`"PREFIX": ["Country", lat, lon]`. If a QSL comes in from a country not
on the list, add it there (no need to touch Python code). Also, if
there's a locator but the country couldn't be determined any other way,
the app automatically queries OpenStreetMap (free, no API key) as a last
resort.

## 9. Packaging as a .exe to share

```
pip install pyinstaller
pyinstaller --name QSLManager --onefile --windowed ^
  --add-data "static;static" ^
  --add-data "qsl_manager/prefixes.json;qsl_manager" ^
  --add-data "tesseract-bin;tesseract-bin" ^
  app.py
```

The `.exe` (with Tesseract included) ends up in `dist/QSLManager.exe`.
Each person who receives it gets their own independent local database --
nothing is shared between installations unless a central-server mode is
explicitly built later.

**About `tesseract-bin/` and GitHub**: that folder (~90 MB, dozens of
binary files) doesn't go into the repository -- it's in `.gitignore` on
purpose. It's only needed *locally*, on your PC, at build time
(PyInstaller reads it from disk). If someone clones the repo from
scratch and wants to build their own `.exe`, they need to get Tesseract
on their own (installer at https://github.com/UB-Mannheim/tesseract/wiki)
and copy that folder in, or just use their own install by pointing to it
in Settings instead of bundling it.

## Known limitations

- Recognition (Tesseract or AI) is a starting point, not always right --
  especially Tesseract with decorative fonts or busy photo backgrounds.
  By design, you always review/correct before a card is marked verified
  (except eQSL, which comes pre-confirmed).
- AI mode requires internet and respects Google's free tier limits.
- The country prefix table covers the most common DXCC entities, not all
  ~340 that exist -- easy to extend, and locator-based geocoding covers
  a good chunk of the rest.
- The base map (OpenStreetMap/CARTO) has no guaranteed Spanish version
  without adding another provider with its own account (e.g. MapTiler);
  each QSL's own data (country, etc.) is already in Spanish/English
  depending on the app's language setting.
- Grouping/filtering by U.S. state isn't implemented yet (a callsign's
  prefix isn't a reliable indicator of the operator's actual state).
