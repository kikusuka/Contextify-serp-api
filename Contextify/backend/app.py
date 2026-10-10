"""
Contextify backend (Role 1: Backend Lead)

Flow for POST /analyze:
  1. Gemini extracts the core claim from the user's message
  2. Fact-check search + regional news search run IN PARALLEL (teammates' modules)
  3. Gemini turns the evidence into: status, summary, red flags, reply message
  4. We rebuild the sources list ourselves from the evidence, so Gemini can never invent a link

Teammates' modules (put next to this file):
  factcheck.py      -> search_factchecks(claim)  -> list of evidence items
  regional_news.py  -> get_regional_news(claim)  -> {"India": [...], "US": [...], "UK": [...]}
Evidence item = {"title", "link", "source", "date", "snippet"}

Run:  python app.py      (from inside the backend folder)
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from google import genai

load_dotenv()

# --- teammates' modules (app still runs if they are not written yet) ---
try:
    from factcheck import search_factchecks
except ImportError:
    def search_factchecks(claim):
        return []

try:
    from regional_news import get_regional_news
except ImportError:
    def get_regional_news(claim):
        return {}

app = Flask(__name__)
CORS(app)  # lets the standalone index.html talk to localhost:5000

# Set GEMINI_MODEL in .env if this model name is retired. Check Google AI Studio for current names.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY) if API_KEY else None

STATUSES = ["Already fact-checked", "Corroborated", "Disputed", "No evidence found"]
_cache = {}  # claim -> result. Saves SerpApi credits while testing and demoing.

EXTRACT_PROMPT = """Extract the single main factual claim from the message below.
Return ONLY the claim as one short plain sentence in English. No quotes, no explanation.
If there are several claims, return the most important checkable one.

Message:
{text}"""

ANALYZE_PROMPT = """You are the analysis engine of Contextify, a tool that helps people check suspicious claims.
You will get the ORIGINAL MESSAGE, the extracted CLAIM, and a numbered list of EVIDENCE found by search.

STRICT RULES
- Use ONLY the evidence given. Never use outside knowledge and never invent facts or sources.
- Choose exactly one status:
  "Already fact-checked": an item of type "factcheck" directly addresses this claim. In the summary say what it concluded.
  "Corroborated": at least two INDEPENDENT outlets (different websites; same wire story copied counts once) report the same core facts.
  "Disputed": credible sources disagree about the facts.
  "No evidence found": evidence is empty, or none of it addresses the claim. Do not guess.
- For political or opinion-heavy claims: separate what can be verified (who said or did what, when) from interpretation or judgement. If coverage is uniformly emotional or loaded, say so and suggest checking the primary source.
- If regions report differently, note the difference briefly. Never say a claim is true or false yourself; report what the evidence shows.
- "source_ids" must only contain ids from the evidence list, the most relevant 3 to 6.
- "red_flags": 0 to 4 short warning signs in the ORIGINAL MESSAGE itself (urgency like "forward to 10 people", no source, emotional language, too good to be true, etc). Empty list if none.
- "reply_message": 1 to 3 polite, non-confrontational sentences the user can send back to whoever forwarded it. Mention what the evidence shows. No blame.
- Write in simple English. "summary" is 2 to 4 sentences.

Return ONLY valid JSON in exactly this shape:
{{"status": "...", "summary": "...", "source_ids": ["E1"], "red_flags": ["..."], "reply_message": "..."}}

ORIGINAL MESSAGE:
{text}

CLAIM:
{claim}

EVIDENCE:
{evidence}
"""


def ask_gemini(prompt, json_mode=False):
    config = {"temperature": 0.2}
    if json_mode:
        config["response_mime_type"] = "application/json"
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
    return resp.text or ""


def extract_claim(text):
    try:
        claim = ask_gemini(EXTRACT_PROMPT.format(text=text)).strip().strip('"')
        return claim or text[:300]
    except Exception:
        return text[:300]  # fall back to the raw message so the app still works


def safe_call(fn, claim, fallback, label, missing):
    try:
        return fn(claim)
    except Exception as e:
        missing.append(f"{label} search failed: {e}")
        return fallback


def gather_evidence(claim):
    """Runs both searches in parallel. Returns (numbered evidence list, list of problems)."""
    missing = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_fc = pool.submit(safe_call, search_factchecks, claim, [], "Fact-check", missing)
        f_rg = pool.submit(safe_call, get_regional_news, claim, {}, "Regional news", missing)
        factchecks, regions = f_fc.result(), f_rg.result()

    # Regional module may return {"India": [...]} or {"regions": {...}, "errors": {...}}
    if isinstance(regions, dict) and "regions" in regions:
        for name, err in (regions.get("errors") or {}).items():
            missing.append(f"{name} news search failed: {err}")
        regions = regions["regions"]
    if not isinstance(regions, dict):
        regions = {}

    def usable(item):  # skip junk and fake mock data so it never reaches Gemini
        return isinstance(item, dict) and not item.get("is_mock") and item.get("link")

    def normalise(item):  # accept both "source" and "source_name"
        return {**item, "source": item.get("source") or item.get("source_name") or ""}

    evidence = []
    for item in factchecks or []:
        if usable(item):
            evidence.append({**normalise(item), "type": "factcheck", "region": "Fact-checker"})
    for region, items in regions.items():
        for item in items if isinstance(items, list) else []:
            if usable(item):
                evidence.append({**normalise(item), "type": "news", "region": region})
    for i, item in enumerate(evidence, 1):
        item["id"] = f"E{i}"
    return evidence, missing


def evidence_for_prompt(evidence):
    lines = []
    for e in evidence:
        lines.append(json.dumps({
            "id": e["id"], "type": e["type"], "region": e["region"],
            "source": e.get("source", ""), "date": e.get("date", ""),
            "title": e.get("title", ""), "snippet": e.get("snippet", ""),
        }, ensure_ascii=False))
    return "\n".join(lines) if lines else "(no evidence found)"


def build_result(text, claim, evidence, missing):
    if not evidence:  # nothing to analyse: say so honestly, and skip the Gemini call
        return {
            "claim": claim,
            "status": "No evidence found",
            "summary": "We could not find credible coverage or fact-checks of this claim. "
                       "That does not prove it is false, but treat it with caution until a trusted source confirms it.",
            "sources": [],
            "red_flags": [],
            "reply_message": "I could not find any trusted source confirming this. "
                             "Could you share where it came from before we pass it on?",
        }

    raw = ask_gemini(
        ANALYZE_PROMPT.format(text=text, claim=claim, evidence=evidence_for_prompt(evidence)),
        json_mode=True,
    )
    data = json.loads(raw.replace("```json", "").replace("```", "").strip())

    by_id = {e["id"]: e for e in evidence}
    sources = [{
        "title": by_id[i].get("title", ""), "link": by_id[i].get("link", ""),
        "source": by_id[i].get("source", ""), "date": by_id[i].get("date", ""),
        "region": by_id[i]["region"], "type": by_id[i]["type"],
        "snippet": by_id[i].get("snippet", ""),
    } for i in data.get("source_ids", []) if i in by_id]  # unknown ids are dropped

    status = data.get("status")
    if status not in STATUSES:
        status = "No evidence found"

    return {
        "claim": claim,
        "status": status,
        "summary": data.get("summary", ""),
        "sources": sources,
        "red_flags": [str(x) for x in data.get("red_flags", [])][:4],
        "reply_message": data.get("reply_message", ""),
    }


@app.get("/health")
def health():
    return jsonify({"ok": True, "model": GEMINI_MODEL, "gemini_key_loaded": client is not None})


@app.post("/analyze")
def analyze():
    if client is None:
        return jsonify({"error": "GEMINI_API_KEY missing. Add it to your .env file."}), 500

    body = request.get_json(silent=True) or {}
    text = (body.get("claim") or "").strip()[:2000]
    if not text:
        return jsonify({"error": "Please paste a claim to check."}), 400

    if text in _cache:
        return jsonify({**_cache[text], "meta": {**_cache[text]["meta"], "cached": True}})

    try:
        claim = extract_claim(text)
        evidence, missing = gather_evidence(claim)
        result = build_result(text, claim, evidence, missing)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 502

    result["meta"] = {
        "missing": missing,
        "evidence_count": len(evidence),
        "regions_searched": sorted({e["region"] for e in evidence}),
        "cached": False,
    }
    _cache[text] = result
    return jsonify(result)


if __name__ == "__main__":
    app.run(port=5000, debug=True)
