from fastapi import APIRouter
from app.schemas.search import SearchRequest, BusinessOut
from app.services import maps_scraper

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=list[BusinessOut])
def search_businesses(request: SearchRequest):
    query = maps_scraper.build_query(
        city=request.city,
        area=request.area,
        category=request.category,
        keyword=request.keyword,
    )

    results = maps_scraper.scrape(query=query, max_results=request.max_results)
    return results