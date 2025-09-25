"""DatasetExportJob dataclass for AI training data export."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4


@dataclass
class DatasetExportJob:
    """Represents a request to package labeled imagery and annotations for download."""
    
    job_id: UUID = field(default_factory=uuid4)
    requested_formats: List[str] = field(default_factory=list)  # subset of {coco-json, yolo-txt}
    status: str = "queued"  # queued, running, complete, failed
    image_count: int = 0
    submitted_by: str = ""  # OperatorCredential.id
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    artifact_urls: Dict[str, str] = field(default_factory=dict)  # keyed by format
    
    def __post_init__(self):
        """Validate DatasetExportJob fields."""
        valid_formats = {"coco-json", "yolo-txt"}
        if not self.requested_formats:
            raise ValueError("requested_formats must contain at least one format")
        if not set(self.requested_formats).issubset(valid_formats):
            raise ValueError(f"requested_formats must be subset of {valid_formats}")
        if self.status not in ["queued", "running", "complete", "failed"]:
            raise ValueError("Invalid status value")