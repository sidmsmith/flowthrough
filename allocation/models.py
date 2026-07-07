from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class PartParams:
    item_id: str
    pack_qty: Optional[Decimal] = None
    pallet_qty: Optional[Decimal] = None
    allow_split_pack: bool = False
    crossdock_preference: str = "full_pallet_first"
    min_order_qty: Decimal = Decimal("1")
    over_max_tolerance: Decimal = Decimal("0")
    default_algorithm: Optional[str] = None


@dataclass
class FacilityNeed:
    facility_suffix: str
    facility_id: str
    priority: int
    item_id: str
    max_qty: Decimal
    available_qty: Decimal
    inbound_qty: Decimal
    outbound_qty: Decimal
    inventory_position: Decimal
    shortage: Decimal
    pack_qty: Decimal
    pallet_qty: Decimal
    allow_split_pack: bool
    over_max_tolerance: Decimal


@dataclass
class AllocationResult:
    algorithm: str
    allocations: Dict[str, Decimal] = field(default_factory=dict)
    residual_qty: Decimal = Decimal("0")
    crossdock_recommendations: List[dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    trace: Optional[dict] = None

    def to_dict(self):
        return {
            "algorithm": self.algorithm,
            "allocations": {k: str(v) for k, v in self.allocations.items()},
            "residual_qty": str(self.residual_qty),
            "crossdock_recommendations": self.crossdock_recommendations,
            "notes": self.notes,
            "trace": self.trace,
        }
