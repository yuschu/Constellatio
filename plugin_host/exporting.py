"""表格导出：CSV / XLSX / PDF 三档共用。

所有导出的数据由调用方先按业务权限和筛选条件取好；这里只负责把二维表写进
响应。CSV 带 UTF-8 BOM（Excel 直接双击也能认出中文），XLSX 冻结表头并开启
筛选，PDF 用中文 CID 字体按横向 A4 排版，长哈希自动折行。
"""

from __future__ import annotations

import csv
import io

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

PDF_FONT = 'STSong-Light'
pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT))
PDF_BODY_STYLE = ParagraphStyle(
    'export-body', fontName=PDF_FONT, fontSize=7.6, leading=10.2,
    textColor=colors.HexColor('#1F2329'), wordWrap='CJK', splitLongWords=1)


def _attachment_header(filename: str) -> str:
    return f'attachment; filename="{filename}"'


def csv_response(filename: str, columns, rows) -> HttpResponse:
    """CSV（UTF-8 BOM）。rows 为可迭代的二维值。"""
    rows = list(rows)
    buffer = io.StringIO()
    buffer.write('\ufeff')
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow(['' if value is None else str(value) for value in row])
    response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = _attachment_header(filename)
    return response


def xlsx_response(filename: str, sheet_name: str, columns, rows, widths=None) -> HttpResponse:
    """单工作表 XLSX。widths 为字符宽度列表，缺省按内容长度估算。"""
    rows = list(rows)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = (sheet_name or 'Sheet1')[:31]
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = 'A2'
    sheet.append(list(columns))

    header_fill = PatternFill('solid', fgColor='F2F3F5')
    for cell in sheet[1]:
        cell.font = Font(name='Calibri', size=11, bold=True, color='1F2329')
        cell.fill = header_fill
        cell.alignment = Alignment(vertical='center')
    sheet.row_dimensions[1].height = 24

    for row in rows:
        sheet.append(['' if value is None else value for value in row])

    for index, column in enumerate(columns, start=1):
        if widths and index <= len(widths):
            width = widths[index - 1]
        else:
            longest = len(str(column))
            for row in rows:
                if index <= len(row):
                    longest = max(longest, len(str(row[index - 1] or '')))
            width = min(max(longest + 2, 10), 60)
        sheet.column_dimensions[get_column_letter(index)].width = width

    buffer = io.BytesIO()
    workbook.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = _attachment_header(filename)
    return response


def _cell(value) -> Paragraph:
    text = '' if value is None else str(value)
    text = (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('\r\n', '<br/>').replace('\n', '<br/>'))
    return Paragraph(text, PDF_BODY_STYLE)


def _normalised_widths(columns, widths, available: float):
    ratios = list(widths or [1] * len(columns))
    if len(ratios) < len(columns):
        ratios.extend([1] * (len(columns) - len(ratios)))
    total = float(sum(ratios)) or 1.0
    return [available * ratio / total for ratio in ratios]


def pdf_response(filename: str, title: str, columns, rows, subtitle: str = '',
                 widths=None) -> HttpResponse:
    """横向 A4 PDF，表头重复，长文本/哈希按列宽折行。"""
    rows = list(rows)
    buffer = io.BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=page,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=title, author='Constellatio')

    title_style = ParagraphStyle(
        'export-title', fontName=PDF_FONT, fontSize=16, leading=22,
        textColor=colors.HexColor('#0F1115'), spaceAfter=4)
    subtitle_style = ParagraphStyle(
        'export-subtitle', fontName=PDF_FONT, fontSize=9, leading=13,
        textColor=colors.HexColor('#81858C'), spaceAfter=10)

    story = [Paragraph(title, title_style)]
    if subtitle:
        story.append(Paragraph(subtitle, subtitle_style))
    else:
        story.append(Spacer(1, 6))

    available = page[0] - doc.leftMargin - doc.rightMargin
    table_data = [[_cell(column) for column in columns]]
    for row in rows:
        table_data.append([_cell(value) for value in row])

    table = LongTable(
        table_data, colWidths=_normalised_widths(columns, widths, available),
        repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F2F3F5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1F2329')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D9DCE1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    story.append(table)
    doc.build(story)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = _attachment_header(filename)
    return response


EXPORT_FORMATS = ('csv', 'xlsx', 'pdf')


def export_response(fmt: str, *, filename, title, columns, rows, subtitle='',
                    sheet_name='导出', widths=None):
    """按格式分发；未知格式返回 None，由视图给 400。"""
    fmt = (fmt or '').lower()
    if fmt == 'csv':
        return csv_response(f'{filename}.csv', columns, rows)
    if fmt == 'xlsx':
        return xlsx_response(f'{filename}.xlsx', sheet_name, columns, rows, widths=widths)
    if fmt == 'pdf':
        return pdf_response(
            f'{filename}.pdf', title, columns, rows,
            subtitle=subtitle, widths=widths)
    return None
