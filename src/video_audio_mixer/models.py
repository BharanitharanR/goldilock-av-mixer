from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class OutputDurationPolicy(str, Enum):
    VIDEO = "video"
    MUSIC = "music"
    SHORTEST = "shortest"
    LONGEST = "longest"


class DuckingSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    music_gain_db: float = Field(ge=-60, le=12)
    reason: str = ""

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class MixPlan(BaseModel):
    schema_version: str = "1.0"
    purpose: str
    output_duration_policy: OutputDurationPolicy = OutputDurationPolicy.VIDEO
    original_audio_enabled: bool = True
    original_audio_gain_db: float = Field(default=0.0, ge=-60, le=12)
    music_enabled: bool = True
    music_gain_db: float = Field(default=-12.0, ge=-60, le=12)
    music_start_seconds: float = Field(default=0.0, ge=0)
    music_end_seconds: float | None = Field(default=None, ge=0)
    music_fade_in_seconds: float = Field(default=0.0, ge=0)
    music_fade_out_seconds: float = Field(default=0.0, ge=0)
    ducking: list[DuckingSegment] = Field(default_factory=list)
    # Music eases into and out of each ducking segment over this long, instead
    # of jumping at its edges.
    ducking_ramp_seconds: float = Field(default=0.25, ge=0, le=5)
    # Integrated loudness of the finished mix (EBU R128 / LUFS); None leaves it.
    output_loudness_lufs: float | None = Field(default=None, ge=-40, le=-5)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plan(self):
        if self.music_end_seconds is not None and self.music_end_seconds < self.music_start_seconds:
            raise ValueError("music_end_seconds cannot precede music_start_seconds")
        return self


class EvaluationResult(BaseModel):
    status: str
    acceptable: bool | None = None
    findings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class MixingContext(BaseModel):
    video_path: str
    music_path: str
    analysis: dict[str, Any]
    song_spec: dict[str, Any]

    @property
    def duration_seconds(self) -> float | None:
        return (
            self.analysis.get("video", {})
            .get("dimensions", {})
            .get("technical", {})
            .get("duration_seconds")
        )
