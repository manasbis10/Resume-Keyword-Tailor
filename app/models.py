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


class LatexChange(BaseModel):
    id: str = Field(max_length=32)
    before: str = Field(min_length=1, max_length=24000)
    after: str = Field(min_length=1, max_length=24000)
    reason: str = Field(default="", max_length=1000)


class RejectedLatexChange(BaseModel):
    id: str = ""
    before: str = ""
    after: str = ""
    reason: str


class LatexProposal(BaseModel):
    changes: list[LatexChange] = Field(default_factory=list, max_length=160)
    rejected_changes: list[RejectedLatexChange] = Field(default_factory=list, max_length=160)
    notes: str = Field(default="", max_length=4000)
    model_used: str = ""
