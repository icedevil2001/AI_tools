from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class RentalProperty(BaseModel):
    address: str
    price_per_month: float
    bedrooms: float
    bathrooms: float
    square_feet: Optional[float]
    price_per_sqft: Optional[float]
    listing_date: datetime
    neighborhood: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    days_listed: Optional[int] = None
    link: Optional[str] = None