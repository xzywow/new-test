import logging
from data_models import Product


class ProductStore:
    def __init__(self):
        self.products = []
        self.keys = set()

    def add(self, product: Product) -> bool:
        # Title/price alone are not reliable product identities.
        key = product.key or (product.title, product.price, product.page_url)
        if key in self.keys:
            return False
        self.keys.add(key)
        self.products.append(product)
        return True


def configure_logging(path):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(path, encoding='utf-8'), logging.StreamHandler()],
                        force=True)
