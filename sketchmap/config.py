from dataclasses import dataclass, asdict
from typing import Literal, Optional, Tuple

from .elements import legend_entries

A4_LONG_MM = 297.0
A4_SHORT_MM = 210.0
PIPELINE_BUDGET_S = 10.0


@dataclass
class Config:
    work_max_side: int = 1100
    min_noise_area: int = 10
    symbol_min_frac: float = 0.012
    symbol_max_frac: float = 0.07
    rdp_eps_frac: float = 0.004
    spur_frac: float = 0.015
    min_stroke_frac: float = 0.012
    jag_amp_frac: float = 0.0045
    jag_min_flips: int = 3
    snap_tol_cells: float = 0.6
    min_seg_cells: float = 0.75
    cell_mm: float = 8.0
    size_small_cells: int = 400
    size_medium_cells: int = 1000
    export_tile_px: int = 32


LEGEND = legend_entries()


@dataclass
class PreprocessParams:
    rotation_deg: float = 0.0
    perspective_points: Optional[Tuple[
        Tuple[float, float],
        Tuple[float, float],
        Tuple[float, float],
        Tuple[float, float],
    ]] = None
    crop_margins: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    shadow_removal: float = 0.35
    brightness: int = 0
    contrast: float = 1.0
    gamma: float = 1.0
    clahe_strength: float = 0.0

    denoise_strength: int = 1
    threshold_mode: Literal["adaptive_gaussian", "adaptive_mean", "otsu", "manual"] = "adaptive_gaussian"
    adaptive_block_size: int = 31
    threshold_offset: int = 12
    invert: Literal["auto", "normal", "invert"] = "auto"

    close_gaps_px: int = 0
    stroke_adjust_px: int = 0
    min_speckle_area: int = 25
    fill_pinholes: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PreprocessParams":
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)
