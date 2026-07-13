import logging
import time

from fastapi import APIRouter, HTTPException

from app.schemas.osint import OsintSearchRequest
from app.services.osint import run_osint_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/osint", tags=["osint"])


@router.post("/search")
def search_business(request: OsintSearchRequest):
    if not request.business_name.strip() or not request.location.strip():
        logger.warning("Rejected request — missing business_name/location: %s", request.dict())
        raise HTTPException(status_code=400, detail="business_name and location are required")

    logger.info("🔍 New OSINT search: '%s' @ '%s'", request.business_name, request.location)
    start = time.time()

    try:
        result = run_osint_search(
            business_name=request.business_name,
            location=request.location,
            address=request.address,
        )
    except Exception:
        logger.exception("OSINT search failed for '%s'", request.business_name)
        raise HTTPException(status_code=500, detail="Internal error while running OSINT search")

    elapsed = time.time() - start
    logger.info("✅ OSINT done in %.2fs", elapsed)
    return result


@router.get("/health")
def health():
    return {"status": "ok"}