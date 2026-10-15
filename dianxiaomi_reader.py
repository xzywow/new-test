"""Configurable, conservative reader. No business-action buttons are clicked."""
import logging
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from data_models import Product
from storage import ProductStore

DEFAULT_SELECTORS = {
    'rows': 'table tbody tr',
    'title': '[data-field="title"], .product-title, .goods-title',
    'source': 'a[href*="aliexpress.com/"]',
    'price': '[data-field="price"], .price',
    'id': '[data-field="product-id"], .product-id',
}


def source_identity(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'}:
        return '', ''
    host = (parsed.hostname or '').lower()
    if host != 'aliexpress.com' and not host.endswith('.aliexpress.com'):
        return '', ''
    match = re.search(r'/item/(\d+)\.html', parsed.path)
    identity = match.group(1) if match else ''
    return parsed._replace(query='', fragment='').geturl(), identity


def parse_products(html, page_url='', selectors=None):
    selectors = {**DEFAULT_SELECTORS, **(selectors or {})}
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    for row in soup.select(selectors['rows']):
        try:
            def value(name):
                node = row.select_one(selectors[name])
                return node.get_text(' ', strip=True) if node else ''
            title = value('title')
            link = row.select_one(selectors['source'])
            source, source_id = source_identity(urljoin(page_url, link.get('href', ''))) if link else ('', '')
            product_id = row.get('data-product-id', '') or value('id') or source_id
            if not title or not (source or product_id):
                logging.warning('Skipped row without title and reliable identity')
                continue
            products.append(Product(str(product_id), title, source, value('price'), page_url))
        except Exception:
            logging.exception('Failed to parse product row')
    return products


class DianxiaomiReader:
    def __init__(self, selectors=None, max_pages=100, next_selector=None):
        self.selectors = {**DEFAULT_SELECTORS, **(selectors or {})}
        self.max_pages = max_pages
        # Pagination is manual by default. A supplied selector must select a
        # navigation anchor, never a button or JavaScript action.
        self.next_selector = next_selector
        self.store = ProductStore()

    def read(self, page, advance=None):
        seen_pages = set()
        for index in range(self.max_pages):
            page.wait_for_selector(self.selectors['rows'], state='visible', timeout=15000)
            # Only visible rows are passed to the HTML parser.
            rows = page.locator(self.selectors['rows']).evaluate_all(
                '(rows) => rows.filter(r => r.getClientRects().length && getComputedStyle(r).visibility !== "hidden").map(r => r.outerHTML)')
            products = parse_products('<table><tbody>' + ''.join(rows) + '</tbody></table>', page.url, self.selectors)
            fingerprint = tuple((p.product_id, p.source_url, p.title, p.price) for p in products)
            if not products:
                raise RuntimeError('未识别到商品，请检查页面和 selectors.json；不会把零条结果当作读取成功。')
            if fingerprint in seen_pages:
                logging.warning('Repeated page detected; stopped pagination')
                break
            seen_pages.add(fingerprint)
            added = sum(self.store.add(product) for product in products)
            logging.info('Page %s: parsed %s, added %s', index + 1, len(products), added)
            if index + 1 == self.max_pages:
                logging.warning('Reached configured page limit')
                break
            if self.next_selector:
                links = page.locator(self.next_selector)
                if links.count() == 0:
                    break
                if links.count() != 1:
                    raise RuntimeError('下一页选择器必须唯一')
                link = links.first
                if link.get_attribute('aria-disabled') == 'true':
                    break
                tag = link.evaluate('(node) => node.tagName.toLowerCase()')
                href = link.get_attribute('href') or ''
                target = urljoin(page.url, href)
                old, new = urlsplit(page.url), urlsplit(target)
                if tag != 'a' or not href or href.startswith(('#', 'javascript:')) or (old.scheme, old.netloc, old.path) != (new.scheme, new.netloc, new.path) or target == page.url:
                    raise RuntimeError('拒绝不安全的分页链接；请改用手动分页')
                page.goto(target, wait_until='domcontentloaded')
            elif advance is None or not advance():
                break
        return self.store.products
