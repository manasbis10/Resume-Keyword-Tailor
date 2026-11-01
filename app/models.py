from typing import Literal

from pydantic import BaseModel, Field


class Experience(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    school: str = ""
    degree: str = ""
    dates: str = ""
    details: str = ""


class TailoredResume(BaseModel):
    name: str = ""
    contact: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    extra_sections: dict[str, list[str]] = Field(default_factory=dict)
    keywords_used: list[str] = Field(default_factory=list)
    notes: str = ""
    model_used: str = ""


class KeywordVariant(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=4)
    after: str = Field(min_length=1, max_length=24000)


class LatexChange(BaseModel):
    id: str = Field(max_length=32)
    before: str = Field(min_length=1, max_length=24000)
    after: str = Field(min_length=1, max_length=24000)
    reason: str = Field(default="", max_length=1000)
    keywords_added: list[str] = Field(default_factory=list, max_length=80)
    keyword_variants: list[KeywordVariant] = Field(default_factory=list, max_length=16)


class RejectedLatexChange(BaseModel):
    id: str = ""
    before: str = ""
    after: str = ""
    reason: str


class KeywordMatch(BaseModel):
    keyword: str
    status: Literal["present", "supported", "missing"]
    evidence: str = ""
    added: bool = False
    in_output: bool = False


class LatexProposal(BaseModel):
    ai_status: Literal["ready", "unavailable"] = "ready"
    ai_warning: str = ""
    changes: list[LatexChange] = Field(default_factory=list, max_length=160)
    rejected_changes: list[RejectedLatexChange] = Field(default_factory=list, max_length=160)
    keyword_report: list[KeywordMatch] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=4000)
    model_used: str = ""
