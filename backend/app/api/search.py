import logging

from fastapi import APIRouter
from app.schemas.search import SearchRequest, BusinessOut
from app.services import maps_scraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=list[BusinessOut])
def search_businesses(request: SearchRequest):
    logger.info(
        f"Search request received — city={request.city}, area={request.area}, "
        f"category={request.category}, keyword={request.keyword}, "
        f"max_results={request.max_results}"
    )

    query = maps_scraper.build_query(
        city=request.city,
        area=request.area,
        category=request.category,
        keyword=request.keyword,
    )
    logger.info(f"Built query string: '{query}'")

    try:
        results = maps_scraper.scrape(query=query, max_results=request.max_results)
    except Exception:
        logger.exception("Scraping failed with an unhandled exception")
        raise

    logger.info(f"Search complete — {len(results)} businesses returned")
    return results