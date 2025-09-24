from nicegui import ui
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import engine
import json
import re
from pathlib import Path
import base64
import os
from openai import OpenAI

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve this folder as /static so images load reliably (FastAPI mount)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent)), name="static")

# OpenAI setup (expects OPENAI_API_KEY in env). Model can be overridden via GPT_MODEL env.
OPENAI_MODEL = os.getenv('GPT_MODEL', 'gpt-4o')
try:
    oai_client = OpenAI()
except Exception:
    oai_client = None  # gracefully skip GPT if not configured

ui.add_head_html('''
<style>
  :root {
    --fwi-primary: #0ea5a6; /* teal */
    --fwi-accent:  #0b7285; /* deep teal */
  }
  .fwi-button { background: var(--fwi-primary); color: white; }
  .fwi-button:hover { filter: brightness(0.95); }
  .fwi-card { border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; }
</style>
''')

# Helper to fetch markdown section for a given dx_id from guidance.md
def get_guidance_section(dx_id: str) -> str:
    """Return the markdown section for a given dx_id from guidance.md."""
    path = Path(__file__).parent / "guidance.md"
    if not path.exists():
        return "_Guidance file not found._"
    text = path.read_text(encoding="utf-8")
    # Match '## dx_id' header and capture until the next '## ' or end of file
    pattern = rf"^##\s+{re.escape(dx_id)}\s*$([\s\S]*?)(?=^##\s+|\Z)"
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return "_No guidance available for this item yet._"
    return m.group(1).strip()

ALLOWED_DX = list(engine.DISEASES.keys())  # enforce known IDs

def get_gpt_differentials(symptom_ids: list[str], free_text: str, priors: list[dict] | None = None) -> list[dict]:
    """Call GPT to produce [{dx_id,label,confidence,rationale[]}] with confidence in [0,1]."""
    print("GPT DEBUG: model=", OPENAI_MODEL)
    print("GPT DEBUG: symptom_ids=", symptom_ids)
    print("GPT DEBUG: free_text=", (free_text or "").strip()[:300])
    if priors is not None:
        print("GPT DEBUG: priors=", priors)
    if oai_client is None:
        print("GPT DEBUG: oai_client is None (OPENAI_API_KEY not set?)")
        return []
    try:
        sys = (
            "You are a cautious, welfare-first aquaculture triage assistant for Indian Major Carps (IMCs) at grow-out in Andhra Pradesh. "
            "Return only JSON. Do not recommend antibiotics or harsh chemicals by default."
        )
        user = {
            "symptoms": symptom_ids,
            "free_text": free_text or "",
            "engine_priors": priors or [],
            "allowed_dx_ids": ALLOWED_DX,
            "format": {
                "results": [
                    {"dx_id":"string","label":"string","confidence":0.0,"rationale":["string"]}
                ]
            },
            "instructions": (
                "Combine symptom_ids, free_text, and engine_priors to pick ONLY from allowed_dx_ids. "
                "Return 2-5 best candidates. confidence must be 0-1; cap if uncertain. Keep rationale short."
            )
        }
        resp = oai_client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.1,
        )
        # Raw response object can be large; print only the message content
        # print("GPT DEBUG: full response=", resp)
        content = resp.choices[0].message.content
        print("GPT DEBUG: raw content=", content)
        data = json.loads(content)
        results = data.get("results", [])
        print("GPT DEBUG: parsed results=", results)
        out = []
        for r in results:
            dx_id = r.get("dx_id")
            if dx_id not in engine.DISEASES:
                print("GPT DEBUG: skipping unknown dx_id=", dx_id, "known=", list(engine.DISEASES.keys()))
                continue
            conf = float(r.get("confidence", 0))
            conf = max(0.0, min(0.8, conf))  # cap at 0.8 like rules engine
            out.append({
                "dx_id": dx_id,
                "label": engine.DISEASES[dx_id],
                "confidence": round(conf, 2),
                "rationale": r.get("rationale", [])[:3],
            })
        # filter >= 0.30 as requested
        out = [r for r in out if r["confidence"] >= 0.30]
        out.sort(key=lambda x: x["confidence"], reverse=True)
        return out
    except Exception as e:
        import traceback
        print("GPT DEBUG: exception=", repr(e))
        traceback.print_exc()
        return []

def render_brand_header():
    """Render FWI brand header with optional local logo.
    If a file named 'fwi_logo.png' sits next to app.py, it will be shown; otherwise fallback to a text mark.
    """
    logo_path = Path(__file__).parent / 'fwi_logo.png'
    with ui.row().classes('items-center justify-start w-full p-3 rounded mb-4') as header:
        header.props('style="background: linear-gradient(90deg, #0ea5a6 0%, #0ea5a6 60%, #0b7285 100%); color: white;"')
        if logo_path.exists():
            ui.image('/static/fwi_logo.png').props('fit=contain').style('height:40px; width:auto; object-fit:contain;').classes('mr-3')
        else:
            ui.label('🐟').classes('text-2xl mr-2')
        ui.label('Fish Welfare Initiative').classes('text-xl font-semibold')
        ui.space()  # flexible spacer
        ui.label('IMC Disease Triage').classes('text-sm opacity-90')

@app.post("/api/triage")
async def triage(symptoms: list[str]):
    return {"top3": engine.score(symptoms), "disclaimer": "Tentative—do not medicate without clear indication."}

# UI
@ui.page("/")
def main_page():
    render_brand_header()
    ui.label('IMC Disease Triage (V1)').classes('text-2xl font-bold mt-2')
    ui.label('Select the signs you observe, then press Submit. Results and guidance appear below.').classes('text-sm text-gray-700')
    selected = set()
    with ui.column().classes('gap-2 p-4 fwi-card'):
        for s_id, label in sorted(engine.SYMPTOMS.items(), key=lambda x: x[1].lower()):
            ui.checkbox(label, on_change=lambda e, s_id=s_id: (selected.add(s_id) if e.value else selected.discard(s_id)))
    free_text = ui.textarea('Describe any other symptoms or the situation (optional)').props('outlined').classes('w-full')

    results_col = ui.column().classes('mt-4 gap-2')

    def submit():
        payload = sorted(list(selected))
        # Use rules as priors/context for GPT, but prefer GPT as the single output list
        priors = engine.score(payload)
        gpt_results = get_gpt_differentials(payload, free_text.value, priors)
        results_col.clear()
        with results_col:
            unified = gpt_results if gpt_results else priors

            if not unified:
                ui.label("No strong match found yet.").classes("text-lg")
                ui.markdown("_Tip: You can either select a couple of obvious signs (e.g., gasping, white spots) **or** just describe the situation in the box above._")
                if oai_client is None:
                    ui.separator()
                    ui.label('GPT not configured').classes('text-md font-semibold')
                    ui.markdown('Set your **OPENAI_API_KEY** (and optionally `GPT_MODEL`) in the environment to enable GPT-assisted suggestions.').classes('text-sm')
                return

            ui.label("Tentative results").classes("text-xl font-bold")
            for r in unified:
                with ui.column().classes('p-3 border rounded'):
                    ui.label(f"{r['label']} — {int(r['confidence']*100)}% confidence").classes("text-lg font-semibold")
                    if r.get("rationale"):
                        for why in r["rationale"][:3]:
                            ui.label(f"• {why}")
                    md = get_guidance_section(r["dx_id"])
                    ui.markdown(md)

            ui.markdown('> **Note:** These are preliminary—further guidance should be obtained before significant action.').classes('mt-2')

    ui.button("Submit", on_click=submit)

if __name__ in {"__main__", "__mp_main__"}:
    ui.run_with(app)
    ui.run(host="0.0.0.0", port=8080)
