from pydantic import BaseModel, Field


class TechAnswer(BaseModel):
    supported: bool = Field(description="Whether the retrieved passages support the answer.")
    answer: str = Field(max_length=1800, description="Brief steps based only on the passages.")
    citations: list[str] = Field(max_length=3, description="Exact retrieved chunk IDs used by the answer.")
