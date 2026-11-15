"""Machine-readable school plan contract, followed by exact musical validation."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from . import SCHOOLS
from .common import validate


class Section(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    duration: float = Field(gt=0)
    character: Literal['still', 'flowing', 'agitated', 'luminous', 'dissolving']
    density: float = Field(gt=0, le=1)
    pitch_register: list[StrictInt] = Field(alias="register", min_length=2, max_length=2)
    dynamic: Literal['ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff'] | None = None


class SchoolPlan(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    title: str = Field(min_length=1)
    school: str
    seed: StrictInt
    ensemble: str
    duration: float = Field(gt=0)
    tempo: float = Field(gt=0)
    form: list[Section] = Field(min_length=1)
    tonic: float | None = None
    mode: Literal['major', 'minor'] | None = None
    centre: float | None = None
    fundamental: float | None = None
    quotation: dict | None = None
    audio_profile: Literal['native_sfz', 'technique_synthesis'] | None = None
    hall_profile: str | None = None
    study: str | None = None
    held_swell: bool = False
    study_basis: str | None = None
    orchestration: str | list[dict] | None = None
    colour: str | None = None
    doublings: bool = False
    line_roles: dict[str, str] | None = None
    line_colours: dict[str, str] | None = None
    line_instruments: dict[str, str] | None = None
    required_techniques: list[str] | None = None

    @model_validator(mode='after')
    def musical_contract(self):
        if self.school not in SCHOOLS:
            raise ValueError('unknown school')
        if self.school == 'polystylism':
            q = self.quotation or {}
            if not q.get('events') or not q.get('sha256') or q.get('quarters', 0) <= 0:
                raise ValueError('polystylism requires archived quotation events, quarters and SHA-256')
        validate(self.model_dump(exclude_none=True, by_alias=True))
        return self
