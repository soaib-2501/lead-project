import json
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.schemas.search import SearchRequest, BusinessOut
from app.services import maps_scraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=list[BusinessOut])
def search_businesses(request: SearchRequest):
    """Original all-at-once endpoint — kept as-is for backward compatibility."""
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


def _sse(event: str, data: dict) -> str:
    """Formats one Server-Sent Event. Every SSE message needs this exact
    'event: X\\ndata: Y\\n\\n' shape — the blank line at the end is what
    tells the browser's EventSource one message is complete."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/search/stream")
def search_businesses_stream(
    city: str,
    category: str,
    area: Optional[str] = None,
    keyword: Optional[str] = None,
    max_results: int = Query(20, ge=1, le=100),
):
    """
    Streaming version of /search using Server-Sent Events (SSE).

    GET (not POST) is required here because the frontend uses the browser's
    built-in EventSource API to consume this, and EventSource only supports
    GET requests with no custom body — so the search params travel as query
    string parameters instead of a JSON body.

    Emits:
      - one "business" event per scraped business, as soon as it's ready
      - one final "done" event with the total count
      - an "error" event if scraping raises partway through
    """
    logger.info(
        f"Streaming search request — city={city}, area={area}, "
        f"category={category}, keyword={keyword}, max_results={max_results}"
    )

    query = maps_scraper.build_query(city=city, area=area, category=category, keyword=keyword)
    logger.info(f"Built query string: '{query}'")

    def event_generator():
        count = 0
        try:
            for raw_biz in maps_scraper.scrape_stream(query=query, max_results=max_results):
                # Validate/normalize through the same schema as the batch
                # endpoint, so both code paths guarantee the same shape to
                # the frontend regardless of which one it's using.
                biz = BusinessOut(**raw_biz).model_dump()
                count += 1
                yield _sse("business", biz)
            yield _sse("done", {"total": count})
            logger.info(f"Streaming search complete — {count} businesses streamed")
        except Exception as e:
            logger.exception("Streaming scrape failed with an unhandled exception")
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            # Prevents any intermediate proxy (e.g. nginx) from buffering
            # the whole response before sending it — without this, "live"
            # streaming can silently turn back into one big delayed chunk.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )