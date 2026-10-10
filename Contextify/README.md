# Contextify

**Paste a suspicious forward. Get linked evidence, not an opinion.**

Contextify is an evidence-first claim checker built for the **SerpApi India Hackathon 2026** (track: *Knowledge & Public Interest*). It checks whether a claim has already been fact-checked, compares how news outlets in India, the US and the UK cover it, and gives the user a plain-language summary, red flags, and a polite reply they can send back to whoever forwarded it.

It never states a verdict without sources, and "No evidence found" is a valid answer.

## The problem

Misleading forwards spread in seconds, but checking one means opening many tabs and judging many sources. Most people don't, so recycled hoaxes keep circulating. Contextify turns that into a single paste.

## What you get

For each claim:

- a status: **Already fact-checked / Corroborated / Disputed / No evidence found**
- a short summary based only on the evidence found
- linked sources (fact-checkers and news outlets from three regions)
- red flags in the message itself (urgency, no source, miracle claims...)
- a ready-to-send, non-confrontational reply with a copy button

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

Design choices that keep it honest:

- **Fact-checkers first.** Many forwards are recycled, so existing fact-checks are the fastest, most reliable answer.
- **Allowlist.** Fact-check results are only accepted from a curated list of sites (`backend/factcheck_sites.json`). Broad news sites only count inside their fact-check section.
- **No invented links.** Gemini only picks evidence IDs; the backend attaches the real links itself.
- **No evidence, no guessing.** If searches return nothing, the app says so without calling the AI.
- **Regional comparison.** The same story searched from three countries shows differences in coverage and framing.
- **Graceful failures.** If one search fails, the others still run and the result reports what was missing.

## How Contextify uses SerpApi

SerpApi is the only source of evidence in the app. Each new claim uses these searches:

| Engine | Parameters | Purpose |
|---|---|---|
| `google` | `site:` filters over fact-check domains, `gl=in` (2 queries) | Has this been fact-checked already? |
| `google_news` | `gl=in`, `gl=us`, `gl=gb` (3 queries, parallel) | How do outlets in each region cover it? |

That is about 5 SerpApi searches per new claim. Repeated claims are cached in memory to save credits.

## Run it locally

You need Python 3.10+, a [SerpApi](https://serpapi.com) key and a [Google AI Studio](https://aistudio.google.com) (Gemini) key.

```bash
git clone https://github.com/kikusuka/Contextify.git
cd Contextify/backend
python -m venv venv
# Windows: venv\Scripts\activate    macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # Windows: copy .env.example .env
# open .env and paste your own keys (never commit this file)

python app.py
```

Check `http://localhost:5000/health`. It should show `"gemini_key_loaded": true`.

Then open `frontend/index.html` in your browser (just double-click it), paste a claim, and press **Check**.

Notes:

- The default Gemini model is `gemini-2.5-flash`. If it is retired, set `GEMINI_MODEL` in `.env` to a current model name.
- To preview the interface without keys, set `USE_SAMPLE = true` at the top of `frontend/script.js`.
- Set `CONTEXTIFY_MOCK=1` to use fake regional news data offline. Mock data is always labelled and never sent to the AI.

## Tests

```bash
cd Contextify          # repo root
python -m unittest discover -v
```

## Project structure

```
backend/
  app.py                 Flask server, Gemini prompts, result assembly
  factcheck.py           fact-check search (SerpApi google + site: filters)
  factcheck_sites.json   curated fact-check site list
  regional_news.py       regional news search (SerpApi google_news, 3 countries)
  sample_result.json     example response
frontend/
  index.html, style.css, script.js
tests/                   unit tests for the two search modules
```

## Limitations and future work

- Contextify checks claims against published evidence. It cannot judge opinions, intent or very new claims with no coverage.
- Politically charged stories are often covered in a uniform, loaded way; agreement between outlets is not proof. The summary separates verifiable events from interpretation where it can.
- Not built yet: image/reverse-image checking, a shareable result card, Hindi and Tamil support, per-outlet bias labels.
- Inspired by tools such as Ground News and The Balanced News, which work at the story level. Contextify works at the claim level.

## AI tools used

- Gemini (runtime): claim extraction and evidence summarisation inside the app.
- Claude (Anthropic): project planning and help writing and reviewing code.
- Teammates also used AI assistants while writing their modules: *(each person: add the tool and what you used it for)*.

## Team

*(add names and roles)*

## Licence

MIT. See [LICENSE](LICENSE).
