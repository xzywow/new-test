import json
from pathlib import Path
from openpyxl import Workbook


def export_products(products, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records = [p.to_dict() for p in products]
    json_path, excel_path = directory / 'products.json', directory / 'products.xlsx'
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Products'
    fields = ['product_id', 'title', 'source_url', 'price', 'page_url']
    sheet.append(fields)
    for record in records:
        # Force text cells: untrusted titles must never become Excel formulas.
        sheet.append([str(record[field]) for field in fields])
        for cell in sheet[sheet.max_row]:
            cell.data_type = 's'
    workbook.save(excel_path)
    return json_path, excel_path
