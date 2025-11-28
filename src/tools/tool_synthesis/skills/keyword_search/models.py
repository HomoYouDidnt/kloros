# skills/keyword_search/models.py
from pydantic import BaseModel, Field, conint
from typing import List

class InputModel(BaseModel):
    """Input model for keyword search tool."""
    query: str = Field(..., min_length=1, max_length=2000,
                      description="Search query string")
    top_k: conint(ge=1, le=50) = Field(10,
                                       description="Maximum number of results to return")

class Item(BaseModel):
    """Search result item."""
    id: str = Field(..., description="Unique identifier for the result")
    filename: str = Field(..., description="File or source name")
    snippet: str = Field(..., description="Relevant text snippet")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score")

class OutputModel(BaseModel):
    """Output model for keyword search tool."""
    items: List[Item] = Field(default_factory=list,
                              description="List of search results")
    total_found: int = Field(..., ge=0,
                             description="Total number of matches found")
    truncated: bool = Field(False,
                            description="Whether results were truncated to top_k")
