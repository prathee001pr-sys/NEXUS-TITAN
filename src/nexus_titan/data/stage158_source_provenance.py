"""Stage 158: data lineage declaration; not an authenticity certificate."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import re

@dataclass(frozen=True)
class ProvenanceReceipt:
    accepted: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

def validate_provenance(*, provider: str, dataset_id: str, retrieved_at: datetime,
                        sha256: str, license_confirmed: bool = False) -> ProvenanceReceipt:
    errors = []
    if not isinstance(provider, str) or not provider.strip() or len(provider) > 160: errors.append('invalid provider')
    if not isinstance(dataset_id, str) or not dataset_id.strip() or len(dataset_id) > 256: errors.append('invalid dataset id')
    if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        errors.append('retrieval timestamp must be timezone aware')
    elif retrieved_at.astimezone(timezone.utc) > datetime.now(timezone.utc): errors.append('retrieval timestamp in future')
    if not isinstance(sha256, str) or re.fullmatch(r'[0-9a-f]{64}', sha256) is None: errors.append('invalid sha256')
    if type(license_confirmed) is not bool: errors.append('invalid license flag')
    warnings = ('Provider identity and dataset authenticity not independently verified.',)
    if license_confirmed is not True: warnings += ('Usage license not confirmed.',)
    return ProvenanceReceipt(not errors, tuple(errors), warnings)
