"""
api.py
------
FastAPI backend for the Bias Detection Engine.

Endpoints
---------
GET  /         — health check
POST /upload   — receive a CSV, clean it via clean_trades.py,
                 then save the cleaned version to uploads/.

Run with:
    uvicorn api:app --reload --port 8000
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from clean_trades import clean

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Bias Detection Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "Bias Detection Engine API"}


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    1. Accept a CSV file from the frontend.
    2. Write it to a temp file so clean_trades can read it.
    3. Run clean_trades.clean() on it.
    4. Save the cleaned DataFrame to uploads/<original_filename>.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    # Write the raw upload to a temp file for cleaning
    raw_bytes = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = Path(tmp.name)

    try:
        cleaned_df = clean(str(tmp_path))
    except ValueError as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)

    destination = UPLOADS_DIR / file.filename
    cleaned_df.to_csv(destination, index=False)

    return {
        "message": f"'{file.filename}' cleaned and saved to uploads/ successfully.",
        "filename": file.filename,
        "original_rows": len(raw_bytes.splitlines()) - 1,
        "clean_rows": len(cleaned_df),
    }
