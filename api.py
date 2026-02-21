"""
api.py
------
FastAPI backend for the Bias Detection Engine.

Endpoints
---------
GET  /           — health check
POST /upload     — receive a CSV, clean it, save to uploads/
POST /analyse    — receive a CSV, clean it, run all detectors, return results

Run with:
    uvicorn api:app --reload --port 8000
"""

import asyncio
import tempfile
from functools import partial
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from clean_trades import clean
from run_all import run_all

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


@app.post("/analyse")
async def analyse_csv(
    file: UploadFile = File(...),
    sensitivity: float = Query(1.5, ge=0.5, le=3.0),
    max_gap: int = Query(2, ge=1, le=5),
):
    """
    1. Accept a CSV file from the frontend.
    2. Clean it via clean_trades.
    3. Save the cleaned file to uploads/.
    4. Run all bias detectors via run_all().
    5. Return structured results as JSON.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

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

    # Run CPU-bound analysis off the async event loop
    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(
            None,
            partial(run_all, str(destination), sensitivity, max_gap),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    # Drop the raw details dict — frontend doesn't need it and it's large
    results.pop("details", None)

    return {
        "filename": file.filename,
        "clean_rows": len(cleaned_df),
        "sensitivity": sensitivity,
        "max_gap": max_gap,
        **results,
    }
