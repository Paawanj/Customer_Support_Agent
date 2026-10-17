from typing import Literal
from pydantic import BaseModel, Field


class TicketClassification(BaseModel):
    category: Literal["billing", "tech", "general"] = Field(description="The support category.")
    confidence: float = Field(ge=0, le=1, description="Confidence from 0 to 1.")
    reasoning: str = Field(min_length=1, max_length=240, description="A brief reason for the category.")
