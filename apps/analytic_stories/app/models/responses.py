from __future__ import annotations

from pydantic import BaseModel, Field


class StorySummary(BaseModel):
    id: int
    name: str
    slug: str
    description: str = ""
    category: str = ""
    use_case: str = ""
    status: str = ""
    author: str = ""
    date_published: str = ""
    date_updated: str = ""
    detection_count: int = 0
    tactics: list[TacticResponse] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)


class DetectionSummary(BaseModel):
    id: int
    name: str
    slug: str
    description: str = ""
    type: str = ""
    severity: str = ""
    status: str = ""
    author: str = ""
    date_published: str = ""
    date_updated: str = ""


class StoryDetail(StorySummary):
    narrative: str = ""
    references: list[str] = Field(default_factory=list)
    detections: list[DetectionSummary] = Field(default_factory=list)


class DetectionDetail(DetectionSummary):
    search_query: str = ""
    how_to_implement: str = ""
    known_false_positives: str = ""
    references: list[str] = Field(default_factory=list)
    techniques: list[TechniqueResponse] = Field(default_factory=list)
    data_sources: list[DataSourceResponse] = Field(default_factory=list)
    stories: list[StorySummaryBrief] = Field(default_factory=list)


class TacticResponse(BaseModel):
    id: str
    name: str
    url: str = ""
    story_count: int = 0


class TechniqueResponse(BaseModel):
    id: str
    name: str
    tactic_id: str = ""
    url: str = ""


class DataSourceResponse(BaseModel):
    id: int
    name: str
    platform: str = ""


class ProductResponse(BaseModel):
    id: int
    name: str


class StorySummaryBrief(BaseModel):
    id: int
    name: str
    slug: str


class SearchResult(BaseModel):
    id: int
    name: str
    slug: str
    description: str = ""
    rank: float = 0.0


class PaginatedResponse(BaseModel):
    items: list = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class StatsResponse(BaseModel):
    total_stories: int = 0
    total_detections: int = 0
    total_tactics: int = 0
    total_techniques: int = 0
    total_data_sources: int = 0
    total_products: int = 0
    detections_by_severity: dict[str, int] = Field(default_factory=dict)
    detections_by_type: dict[str, int] = Field(default_factory=dict)
    stories_by_category: dict[str, int] = Field(default_factory=dict)
    tactic_coverage: list[TacticResponse] = Field(default_factory=list)


# Rebuild forward refs
StoryDetail.model_rebuild()
DetectionDetail.model_rebuild()
StorySummary.model_rebuild()
