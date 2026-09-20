"""Single-sheet fallback for PCs without the optional artifact runtime."""
from pathlib import Path

def write_workbook(data, target):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.drawing.image import Image
    from openpyxl.utils import get_column_letter as column
    wb = Workbook()
    wb.remove(wb.active)
    for spec in data['sheets']:
        sh = wb.create_sheet(spec['name'])
        sh.sheet_view.showGridLines = False
        sh.freeze_panes = 'D2'
        for i,width in enumerate(spec['widths'],1):
            sh.column_dimensions[column(i)].width = width/7
        for r,values in enumerate([spec['headers'],*spec['rows']],1):
            sh.row_dimensions[r].height = 54 if r == 1 else 34.5
            for c,value in enumerate(values,1):
                cell = sh.cell(r,c)
                cell.value,cell.data_type = str(value),'s'
                cell.font = Font(name='Arial',size=11,bold=r==1,color='17212B')
                cell.alignment = Alignment(vertical='top',wrap_text=True)
                if r==1:
                    cell.fill = PatternFill('solid',fgColor='E2EBF3')
        if spec['rows']:
            sh.auto_filter.ref = f"A1:R{len(spec['rows'])+1}"
            validation = DataValidation(type='list',formula1='"'+','.join(data['review_options'])+'"')
            sh.add_data_validation(validation)
            validation.add(f"P2:P{len(spec['rows'])+1}")
        for pic in spec['images']:
            r = pic['row']+1
            im = Image(pic['path'])
            scale = min(288/im.width,508/im.height)
            im.width,im.height = im.width*scale,im.height*scale
            sh.add_image(im,f'D{r}')
            sh.row_dimensions[r].height = 399
        sh.sheet_properties.pageSetUpPr.fitToPage = True
        sh.page_setup.orientation='landscape'
        sh.page_setup.fitToWidth=1
        sh.page_setup.fitToHeight=0
    wb.save(Path(target))
