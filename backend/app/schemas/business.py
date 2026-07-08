from pydantic import BaseModel
from typing import Optional


class BusinessDetailResponse(BaseModel):
    social_links: dict[str, str] = {}
    og_image: Optional[str] = None
    favicon: Optional[str] = None
    logo: Optional[str] = None
    gallery: list[str] = []