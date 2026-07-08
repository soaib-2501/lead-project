from fastapi import APIRouter, Query
from app.schemas.business import BusinessDetailResponse
from app.services.social_scraper import extract_site_intel

router = APIRouter(prefix="/api", tags=["business"])


@router.get("/business-detail", response_model=BusinessDetailResponse)
def get_business_detail(website: str = Query(..., description="The business's website URL")):
    """
    Called only when a user opens a specific business's detail page.
    Visits that one website to pull social links + logo/og-image/gallery.
    Kept separate from bulk search so the search results table stays fast.
    """
    intel = extract_site_intel(website)

    images = intel.get("images", {})
    return BusinessDetailResponse(
        social_links=intel.get("social_links", {}),
        og_image=images.get("og_image"),
        favicon=images.get("favicon"),
        logo=images.get("logo"),
        gallery=images.get("gallery", []),
    )