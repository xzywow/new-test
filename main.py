import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from browser_manager import BrowserManager
from dianxiaomi_reader import DianxiaomiReader
from export_service import export_products
from storage import configure_logging


def main():
    parser = argparse.ArgumentParser(description='店小秘采集箱只读导出工具')
    parser.add_argument('--selectors', type=Path, help='自定义 CSS 选择器 JSON')
    parser.add_argument('--profile', type=Path, default=Path('.browser-profile'))
    parser.add_argument('--output', type=Path, default=Path('output'))
    parser.add_argument('--max-pages', type=int, default=100)
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error('--max-pages 必须大于零')
    directory = args.output / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    directory.mkdir(parents=True)
    configure_logging(directory / 'reader.log')
    reader = None
    try:
        config = json.loads(args.selectors.read_text(encoding='utf-8')) if args.selectors else {}
        reader = DianxiaomiReader(config.get('selectors'), args.max_pages, config.get('next_selector'))
        with BrowserManager(args.profile, 'https://www.dianxiaomi.com/') as browser:
            input('请手动登录，进入采集箱并等待商品显示。完成后回到这里按 Enter：')
            pages = [page for page in browser.context.pages if not page.is_closed()]
            for i, page in enumerate(pages):
                print(f'{i}: {page.url}')
            selected = input('输入采集箱标签页编号（默认最后一个）：').strip()
            page = pages[int(selected)] if selected else pages[-1]
            browser.protect_read_phase()
            def advance():
                return input('已读取本页。请在浏览器手动切换下一页并等待加载，输入 y 继续；其他输入结束：').lower().strip() == 'y'
            reader.read(page, advance)
        if not reader.store.products:
            raise RuntimeError('未读取到商品')
        paths = export_products(reader.store.products, directory)
        print(f'已导出 {len(reader.store.products)} 条商品：{paths[0]}，{paths[1]}')
        return 0
    except (Exception, KeyboardInterrupt):
        logging.exception('读取未完整完成')
        if reader and reader.store.products:
            export_products(reader.store.products, directory / 'partial')
            logging.warning('已保存部分结果到 partial；此结果不代表完整成功')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
