"""BrandAsset dataclass for retro visual elements in WebUI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class BrandAsset:
    """Metadata for mandated retro visual elements surfaced throughout the WebUI."""
    
    asset_id: str  # e.g., logo-main, icon-status, map-pin
    file_name: str  # e.g., LawnBerryPi_logo.png
    usage_contexts: List[str] = field(default_factory=list)  # WebUIPage.slug references
    format: str = "png"  # png, svg
    dimensions_px: Dict[str, int] = field(default_factory=dict)  # width/height
    color_palette: List[str] = field(default_factory=list)  # hex strings referencing retro palette
    
    def __post_init__(self):
        """Validate BrandAsset fields."""
        if not self.asset_id or not self.file_name:
            raise ValueError("asset_id and file_name are required")
        if self.format not in ["png", "svg"]:
            raise ValueError("format must be 'png' or 'svg'")
        if not self.usage_contexts:
            raise ValueError("usage_contexts must include at least one page")
        
        # Validate headline assets include required contexts
        if self.asset_id in ["logo-main", "icon-status"]:
            required_contexts = {"dashboard", "manual-control"}
            if not required_contexts.issubset(set(self.usage_contexts)):
                raise ValueError(f"Headline asset {self.asset_id} must include dashboard and manual-control contexts")