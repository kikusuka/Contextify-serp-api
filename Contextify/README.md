# Contextify

**Paste a suspicious forward. Get linked evidence, not an opinion.**

Built for the **SerpApi India Hackathon 2026**, track: *Knowledge & Public Interest*.

---

## For judges: 60-second overview

**The problem.** Misleading forwards (WhatsApp, social media) spread in seconds, but checking one means opening many tabs and judging many sources. Most people don't, so recycled hoaxes keep circulating.

**What Contextify does.** The user pastes a claim. The app:

1. extracts the core claim (Gemini),
2. searches fact-checking sites to see if it has **already been debunked** (SerpApi `google`),
3. compares how news outlets in **India, the US and the UK** cover it (SerpApi `google_news`),
4. shows a status, a short summary, linked sources, red flags in the message, and a **ready-to-send polite reply**.

**What makes it different.** Tools like Ground News and The Balanced News work at the *story* level (how outlets cover a news event). Contextify works at the *claim* level: "is this specific forward true, and where is the evidence?" It never states a verdict without sources, and "No evidence found" is a valid answer.

**Where to look first (about 3 minutes):**

1. Follow **Quick start** below and check the three sample claims in **Test it yourself**.
2. Read `backend/app.py` (the pipeline and the Gemini prompt) and the two search modules: `backend/factcheck.py` and `backend/regional_news.py`.
3. Run the unit tests (no API keys needed): `python -m unittest discover -v`.

### How this maps to the judging criteria

| Criterion | What to look at |
|---|---|
| **Idea and usefulness** | One paste replaces opening many tabs. Output includes a reply the user can send back to the person who forwarded it. |
| **Originality** | Claim-level checking; fact-checkers first; cross-region comparison with the `gl` parameter; honest "no evidence" outcome. |
| **Technical complexity** | Parallel SerpApi calls, allowlist filtering of results, path-restricted fact-check sites, evidence-ID system so the AI cannot invent links, failure isolation per search, in-memory caching, 20 unit tests. |
| **Meaningful SerpApi usage** | SerpApi is the *only* source of evidence. Two engines (`google`, `google_news`), 5 searches per new claim. See the table below. |

### How Contextify uses SerpApi

| Engine | Parameters | Purpose |
|---|---|---|
| `google` | `site:` filters over fact-check domains, `gl=in`, 2 queries | Has this claim already been fact-checked? |
| `google_news` | `gl=in`, `gl=us`, `gl=gb`, 3 queries in parallel | How do outlets in each country cover it? |

Without SerpApi there would be no evidence to show: the AI only summarises what the searches return.

### Design choices that keep it honest

- **Fact-checkers first.** Many forwards are recycled, so an existing fact-check is the fastest, most reliable answer.
- **Allowlist.** Fact-check results are only accepted from a curated list (`backend/factcheck_sites.json`). Broad news sites only count inside their fact-check section.
- **No invented links.** Gemini only picks evidence IDs; the backend attaches the real links itself.
- **No evidence, no guessing.** If searches return nothing, the app says so without calling the AI.
- **Graceful failures.** If one search fails, the others still run and the result reports what was missing.
- **Agreement is not proof.** Politically charged stories are often covered in a uniform, loaded way. The prompt separates verifiable events from interpretation and flags uniform, emotional coverage.

---

## Quick start (beginner-friendly)

You will need about 15 minutes. No coding is required.

### Step 1: Install Python

1. Go to https://www.python.org/downloads/ and install Python **3.10 or newer**.
2. On Windows, tick **"Add Python to PATH"** during installation.
3. Check it worked: open a terminal (Windows: search "Command Prompt"; Mac: open "Terminal") and type:

```
python --version
```

If that says "not found" on Windows, try `py --version`. On Mac or Linux, try `python3 --version`. Use whichever works in place of `python` below.

### Step 2: Get the two free API keys

| Key | Where to get it | Free allowance |
|---|---|---|
| **SerpApi** | Sign up at https://serpapi.com, then open your dashboard and copy the API key. | The free plan has a monthly search allowance (250 searches at the time of writing). |
| **Gemini** | Go to https://aistudio.google.com, sign in with a Google account, and choose **Get API key**. | Free tier available. |

> Each *new* claim uses about **5 SerpApi searches**, so the free plan covers roughly 50 checks. Checking the same claim again is served from memory and costs nothing (until the server restarts).

### Step 3: Download the project

Either click **Code, Download ZIP** on GitHub and unzip it, or:

```
git clone https://github.com/kikusuka/Contextify.git
```

### Step 4: Set up the backend

Open a terminal **inside the project folder**, then run these one at a time.

**Windows**

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**Mac / Linux**

```
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Step 5: Add your keys

Open the new file `backend/.env` in any text editor (Notepad is fine) and replace the placeholders:

```
GEMINI_API_KEY=paste_your_gemini_key_here
SERPAPI_API_KEY=paste_your_serpapi_key_here
```

Save the file. Never share this file or upload it to GitHub (it is already ignored by git).

### Step 6: Start the backend

In the same terminal:

```
python app.py
```

Leave it running. Open http://localhost:5000/health in your browser. You should see something like:

```
{"gemini_key_loaded": true, "model": "gemini-2.5-flash", "ok": true}
```

### Step 7: Open the app

Open the `frontend` folder and **double-click `index.html`**. It opens in your browser. Paste a claim and press **Check**.

---

## Test it yourself

Paste each of these into the box and press **Check**. Results come from live searches, so wording and sources will vary, but the *kind* of outcome should be similar. A check usually takes a few seconds up to about 20 seconds.

| # | Paste this | What you should see |
|---|---|---|
| 1 | `Drinking hot water with lemon every morning cures cancer.` | A recycled health hoax. Expect **Already fact-checked** (or **Disputed**), with links to fact-check sites. |
| 2 | A real headline from today's news (copy one from any major news site) | Expect **Corroborated**, with several news sources from different countries. |
| 3 | `NASA confirmed that a second moon will appear in the sky next week.` | Nothing credible exists. Expect **No evidence found**. This is the *correct* answer, not a failure. |

**Then check these things:**

- The loading screen shows steps while it works.
- A coloured **status badge** appears with a short summary.
- Every source in the list is a real link that opens the article.
- **Red flags** appear for suspicious wording (try pasting: `URGENT!! Forward this to 10 people or something bad will happen`).
- **Copy reply** copies a polite message to your clipboard.
- **Error handling:** stop the backend (press Ctrl+C in the terminal), press **Check** again, and you should see a friendly error screen, not a blank page.

### Run the automated tests (no API keys needed)

From the project root:

```
python -m unittest discover -v
```

All tests should pass. They use fake data, so they cost no SerpApi credits.

### Try the interface without any keys

Open `frontend/script.js` and change `const USE_SAMPLE = false;` to `true`. The page then shows built-in sample data and a demo banner. Set it back to `false` for real checks.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not recognised | Reinstall Python and tick "Add to PATH", or use `py` (Windows) / `python3` (Mac, Linux). |
| `venv\Scripts\activate` is blocked on Windows | Use Command Prompt instead of PowerShell, or run `venv\Scripts\activate.bat`. |
| `/health` shows `gemini_key_loaded: false` | The `.env` file is missing or in the wrong place. It must be `backend/.env`, with the key on the line `GEMINI_API_KEY=...` and no quotes. |
| Error mentioning the model name | Gemini model names change. In `backend/.env` add `GEMINI_MODEL=` followed by a current model name from Google AI Studio, then restart. |
| Page says it "could not get a result" | The backend is not running. Start it again with `python app.py` and keep that terminal open. |
| Result says a search "failed" or `SERPAPI_API_KEY is missing` | Check the SerpApi key in `.env` and your remaining SerpApi searches. Restart after editing `.env`. |
| Always "No evidence found" | Make sure the claim is specific. Very vague or brand-new claims often have no coverage. |

---

## How it works

```
 index.html  --POST /analyze-->  Flask backend
                                   |
                  1. Gemini extracts the core claim
                                   |
                  2. in parallel:  +-- SerpApi "google"       -> fact-check sites (site: filters)
                                   +-- SerpApi "google_news"  -> India (gl=in), US (gl=us), UK (gl=gb)
                                   |
                  3. Gemini writes status, summary, red flags, reply (only from the evidence)
                                   |
                  4. backend rebuilds the source list from the real search results
                                   |
 index.html  <------ JSON --------+
```

**Status meanings**

- **Already fact-checked:** a fact-checking site directly addresses this claim.
- **Corroborated:** at least two independent outlets report the same core facts.
- **Disputed:** credible sources disagree about the facts.
- **No evidence found:** nothing credible addresses the claim. This does not prove it is false.

## Project structure

```
backend/
  app.py                 Flask server, Gemini prompts, result assembly
  factcheck.py           fact-check search (SerpApi google + site: filters)
  factcheck_sites.json   curated fact-check site list
  regional_news.py       regional news search (SerpApi google_news, 3 countries)
  sample_result.json     example response
  .env.example           template for your API keys
frontend/
  index.html, style.css, script.js
tests/                   unit tests for the two search modules
```

## Limitations and future work

- Contextify checks claims against published evidence. It cannot judge opinions or intent, and brand-new claims may have no coverage yet.
- Search results come from live Google data and can vary between runs.
- Not built yet: image and reverse-image checking, a shareable result card, Hindi and Tamil support, per-outlet bias labels.

## AI tools used

- **Gemini** (inside the app): claim extraction and summarising the evidence.
- **Claude (Anthropic):** project planning and help writing and reviewing code.
- *(Team: each person adds the AI tool you used and for what.)*

## Team

*(Add names and roles.)*

## Licence

MIT. See [LICENSE](LICENSE).
