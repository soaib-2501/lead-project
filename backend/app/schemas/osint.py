from pydantic import BaseModel
from typing import Optional


class OsintSearchRequest(BaseModel):
    business_name: str
    location: str
    address: Optional[str] = None