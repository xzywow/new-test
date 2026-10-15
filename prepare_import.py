"""Prepare a LOCAL workbook. Never uploads or changes Dianxiaomi records."""
import argparse
import json
from pathlib import Path
from import_rules import SkuRegistry, export_import, validate_record


def main():
    parser = argparse.ArgumentParser(description='生成店小秘模板导入文件，仅本地操作')
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True, help='UTF-8 JSON 商品数组')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--db', type=Path, default=Path('output/sku-registry.sqlite3'))
    args = parser.parse_args()
    registry = None
    try:
        records = json.loads(args.input.read_text(encoding='utf-8-sig'))
        if not isinstance(records, list) or not records or any(not isinstance(r, dict) for r in records):
            raise ValueError('输入必须是非空商品对象数组')
        keys = set()
        for index, record in enumerate(records, 1):
            errors = validate_record(record, allow_missing_sku=True)
            key = record.get('record_key')
            if not isinstance(key, str) or not key.strip() or key in keys:
                errors.append('record_key 必须为非空且不重复的规格标识')
            keys.add(key if isinstance(key, str) else '')
            if errors:
                raise ValueError(f'第{index}条：' + '；'.join(errors))
            if record.get('SKU'):
                raise ValueError('本命令自动分配日期 SKU，请省略输入中的 SKU；现有 SKU 修改需另做映射确认')
        args.db.parent.mkdir(parents=True, exist_ok=True)
        registry = SkuRegistry(args.db)
        for record in records:
            record['SKU'] = registry.assign(record['record_key'])
        export_import(args.template, args.output, records)
        print(f'已生成 {len(records)} 个规格的本地文件：{args.output}；尚未导入店小秘。')
        return 0
    except (ValueError, OSError) as error:
        print('准备失败：', error)
        return 1
    finally:
        if registry:
            registry.close()


if __name__ == '__main__':
    raise SystemExit(main())
