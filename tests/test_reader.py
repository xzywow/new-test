import os
import json
import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
from playwright.sync_api import sync_playwright
from dianxiaomi_reader import parse_products, DianxiaomiReader
from export_service import export_products
from storage import ProductStore
from browser_manager import read_only_route

HTML = '''<table><tbody>
<tr data-product-id="123"><td class="product-title">中文商品</td><td><a href="https://www.aliexpress.com/item/123.html?tracking=x">来源</a></td><td class="price">US $2.50</td></tr>
<tr><td class="product-title">无身份</td></tr>
</tbody></table>'''


class ReaderTests(unittest.TestCase):
    def test_parse_and_deduplicate(self):
        products = parse_products(HTML, 'https://www.dianxiaomi.com/list')
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].title, '中文商品')
        self.assertEqual(products[0].source_url, 'https://www.aliexpress.com/item/123.html')
        self.assertEqual(products[0].price, 'US $2.50')
        store = ProductStore()
        self.assertTrue(store.add(products[0]))
        self.assertFalse(store.add(products[0]))

    def test_export_safe_text(self):
        products = parse_products(HTML)
        products[0].title = '=HYPERLINK("bad")'
        with tempfile.TemporaryDirectory() as directory:
            jp, xp = export_products(products, directory)
            self.assertEqual(json.loads(jp.read_text(encoding='utf-8'))[0]['product_id'], '123')
            book = load_workbook(xp)
            self.assertEqual(book.active['B2'].data_type, 's')
            self.assertEqual(book.active['B2'].value, products[0].title)
            book.close()

    def test_browser_visible_rows_and_manual_pagination(self):
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True, executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH'))
            try:
                page = browser.new_page()
                page.set_content(HTML.replace('</tbody>', '<tr style="display:none" data-product-id="hidden"><td class="product-title">hidden</td></tr></tbody>'))
                calls = []
                def advance():
                    calls.append(1)
                    if len(calls) == 1:
                        page.set_content(HTML.replace('123', '456'))
                        return True
                    return False
                products = DianxiaomiReader().read(page, advance)
                self.assertEqual([p.product_id for p in products], ['123', '456'])
            finally:
                browser.close()

    def test_read_only_network_guard(self):
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True, executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH'))
            try:
                context = browser.new_context(service_workers='block')
                context.route('**/*', read_only_route)
                page = context.new_page()
                page.set_content('<html></html>')
                result = page.evaluate("async () => { try { await fetch('https://example.com/write', {method: 'POST'}); return false; } catch { return true; } }")
                self.assertTrue(result)
            finally:
                browser.close()

    def test_automatic_pagination(self):
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True, executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH'))
            try:
                page = browser.new_page()
                def serve(route):
                    second = 'page=2' in route.request.url
                    html = HTML.replace('123', '456') if second else HTML + '<a class="next" href="?page=2">下一页</a>'
                    route.fulfill(body=html, content_type='text/html')
                page.route('https://example.com/**', serve)
                page.goto('https://example.com/list?page=1')
                products = DianxiaomiReader(next_selector='a.next').read(page)
                self.assertEqual([p.product_id for p in products], ['123', '456'])
            finally:
                browser.close()

    def test_empty_parse(self):
        self.assertEqual(parse_products('<html></html>'), [])

    def test_repeated_page_stops(self):
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True, executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH'))
            try:
                page = browser.new_page()
                page.set_content(HTML)
                self.assertEqual(len(DianxiaomiReader().read(page, lambda: True)), 1)
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
