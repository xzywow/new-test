from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Product:
    product_id: str = ''
    title: str = ''
    source_url: str = ''
    price: str = ''
    page_url: str = ''

    @property
    def key(self) -> Optional[str]:
        return self.product_id or self.source_url or None

    def to_dict(self):
        return asdict(self)
