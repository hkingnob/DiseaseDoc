# IMC-DX (V1 Minimal)

Snapshot, no-storage web app to tentatively triage diseases for Indian Major Carps (IMCs) at the grow-out stage.
- English-only
- No media uploads
- ≤12 symptom checkboxes
- Welfare-first guidance
- Confidence calibrated and capped at **80%**

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:8080/

## Structure
- `app.py` — NiceGUI UI + FastAPI API in one process
- `engine.py` — tiny rules engine + calibration
- `content.yaml` — symptoms, differentials, likelihoods
- `guidance.md` — welfare-first action cards keyed by differential IDs

## Notes
- This V1 stores nothing server-side.
- The UI calls the engine directly (no persistence). There is also a POST `/api/triage` you can use programmatically.
