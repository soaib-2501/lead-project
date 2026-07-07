from pydantic import BaseModel
from typing import Optional


class SearchRequest(BaseModel):
    city: str
    area: Optional[str] = None
    category: str
    keyword: Optional[str] = None
    max_results: int = 20


class BusinessOut(BaseModel):
    place_id: str
    name: str
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    rating: Optional[str] = None
    reviews: Optional[str] = None
    opening_hours: Optional[str] = None