"""Fill original OOXML bug sheets without a formatting roundtrip or extra tabs."""
import copy
import posixpath
import re
import io
import math
import shutil
from collections.abc import MutableMapping
from xml.sax.saxutils import quoteattr
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

from PIL import Image
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.utils.cell import range_boundaries

from .excel_report import annotate
from .util import PilotError, read_json

M='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
D='http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
C='http://schemas.openxmlformats.org/package/2006/content-types'

class WorkbookParts(MutableMapping):
    """Keep unchanged ZIP members on disk; images from other sheets need no RAM copy."""
    def __init__(self,path):
        self.path=path;self.changed={}
        with ZipFile(path) as z:self.names=dict.fromkeys(z.namelist())
    def __getitem__(self,key):
        if key not in self.names:raise KeyError(key)
        if key in self.changed:return self.changed[key]
        with ZipFile(self.path) as z:return z.read(key)
    def __setitem__(self,key,value):self.names[key]=None;self.changed[key]=value
    def __delitem__(self,key):del self.names[key];self.changed.pop(key,None)
    def __iter__(self):return iter(self.names)
    def __len__(self):return len(self.names)
    def __contains__(self,key):return key in self.names
    def pop(self,key,default=None):
        if key in self.names:del self[key]
        return default
    def save(self,path):
        with ZipFile(self.path) as source,ZipFile(path,'w',ZIP_DEFLATED) as target:
            for name in self.names:
                if name in self.changed:target.writestr(name,self.changed[name])
                else:
                    with source.open(name) as src,target.open(name,'w',force_zip64=True) as dst:shutil.copyfileobj(src,dst,1024*1024)
def tag(ns,name): return '{'+ns+'}'+name
def xml(root, original=None):
    # OPC package readers expect an unprefixed root for content types/relationships.
    if root.tag in {tag(C,'Types'),tag(P,'Relationships')}:
        ET.register_namespace('',root.tag[1:].split('}',1)[0])
    # Excel compatibility attributes contain prefix names as values (e.g. mc:Ignorable).
    # ElementTree does not retain declarations used only by those attribute values.
    namespaces={}
    if original:
        for event,value in ET.iterparse(io.BytesIO(original),events=('start-ns','start')):
            if event=='start': break
            prefix,uri=value;namespaces[prefix]=uri
            if prefix and not re.fullmatch(r'ns\d+',prefix): ET.register_namespace(prefix,uri)
    result=ET.tostring(root,encoding='unicode',xml_declaration=True)
    if namespaces:
        opening=result.index('<',result.index('?>')+2)
        end=result.index('>',opening)
        header=result[opening:end]
        extras=[]
        for prefix,uri in namespaces.items():
            attr='xmlns:'+prefix if prefix else 'xmlns'
            if prefix!='xml' and not re.search(r'\s'+re.escape(attr)+r'=',header):
                extras.append(' '+attr+'='+quoteattr(uri))
        result=result[:end]+''.join(extras)+result[end:]
    return result.encode('utf-8')
def part(base,target): return target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(base),target))
def relpath(name): return posixpath.join(posixpath.dirname(name),'_rels',posixpath.basename(name)+'.rels')

def report_id(spec): return spec.get('id',spec['name'])

def shift_range(value,after,amount):
    return re.sub(r'(\$?[A-Z]{1,3}\$?)(\d+)',lambda m:m[1]+str(int(m[2])+amount if int(m[2])>after else int(m[2])),value)

def shift_rows(root,after,amount):
    if not amount:return
    for node in root.iter():
        if node.tag==tag(M,'row') and int(node.attrib['r'])>after:node.set('r',str(int(node.attrib['r'])+amount))
        for key in ('ref','sqref','topLeftCell'):
            if key in node.attrib:node.set(key,shift_range(node.attrib[key],after,amount))
        if node.tag==tag(M,'c'):node.set('r',shift_range(node.attrib['r'],after,amount))

def values_for_cells(item,spec):
    values=dict(item['values']);fields={c['field'] for c in spec['columns']}
    sink=next((k for k in ('description','comment','observed','fix') if k in fields),None)
    if not item['finding']:
        if 'status' not in fields and sink:values[sink]=values['status']
        return values
    missing=[]
    for key,label in [('type','Type'),('observed','Text'),('comment','Issue'),('fix','Fix')]:
        if key not in fields and not ('description' in fields and key!='type'):
            missing.append(label+': '+values.get(key,''))
    if missing and sink:values[sink]='\n'.join([values.get(sink,''),*missing]).strip()
    return values


def set_text(cell,value):
    for child in list(cell): cell.remove(child)
    cell.set('t','inlineStr')
    text=str(value)
    if len(text)>32767: raise PilotError('Testo oltre la capacità di una cella Excel')
    ET.SubElement(ET.SubElement(cell,tag(M,'is')),tag(M,'t'),{'{http://www.w3.org/XML/1998/namespace}space':'preserve'}).text=text


def report_rows(run):
    contract=run['project']['client_workbook']
    route={r['taxonomy_id']:r['sheet'] for r in contract['routes']}
    output={report_id(s):[] for s in contract['sheets']}
    for case in run['project']['cases']:
        result=run['cases'].get(case['id'],{})
        findings=[f for f in result.get('findings',[]) if f['verification']['verdict']=='confirmed']
        for f in findings:
            sheet=route.get(f['taxonomy_id'])
            if sheet not in output: raise PilotError('Manca il foglio cliente per un tipo di bug')
            comment=f['verification'].get('report_comment',f['verification']['explanation'])
            values={'date':run['started_at'][:10],'location':case['title'],'case_id':case['id'],
                'type':f['taxonomy']['name_zh'] or f['taxonomy']['name_en'],'observed':f['observed'],'comment':comment,
                'fix':f['expected'],'description':f"Text: {f['observed']}\nIssue: {comment}\nFix: {f['expected']}",
                'id':f['id'],'priority':f['taxonomy']['priority'],'category':f['taxonomy']['category'],'owner':f['taxonomy']['owner'],
                'status':'Bug' if result.get('coverage')=='complete' else 'Bug (partial)'}
            values['language']=run['project'].get('language','')
            values['steps']='\n'.join(s.get('action',{}).get('target','') for s in result.get('steps',[])[:f.get('step_index',len(result.get('steps',[])))])
            for kind,field in [('dev_keys','dev_key'),('log_keys','log_key')]:
                matches={k['key'] for k in run['project'].get('project_context',{}).get(kind,[])
                         if k.get('value','').strip() and k['value'].strip()==f['observed'].strip()}
                values[field]=next(iter(matches)) if len(matches)==1 else ''
            output[sheet].append({'values':values,'finding':f})
        if not findings:
            output[contract['pass_sheet']].append({'values':{'location':case['title'],'case_id':case['id'],
                'status':'Pass' if result.get('status')=='PASS' else 'Incomplete'},'finding':None})
    return output


def export_client(folder, *, state=None):
    folder=Path(folder).resolve()
    run=state or read_json(folder/'run.json')
    contract=run['project']['client_workbook']
    template=folder/contract.get('run_template','client-template.xlsx')
    if not template.is_file():
        template=Path(contract['template'])
    if not template.is_file(): raise PilotError('Template originale non disponibile per il report')
    files=WorkbookParts(template)
    workbook=ET.fromstring(files['xl/workbook.xml']); rels=ET.fromstring(files['xl/_rels/workbook.xml.rels'])
    relations={e.attrib['Id']:part('xl/workbook.xml',e.attrib['Target']) for e in rels}
    keep={s['name'] for s in contract['sheets']}
    book_sheets=workbook.find(tag(M,'sheets')); selected={}
    old_positions={s.attrib['name']:i for i,s in enumerate(book_sheets)}
    for sh in list(book_sheets):
        rid=sh.attrib[tag(R,'id')]; path=relations[rid]
        if sh.attrib['name'] in keep:
            selected[sh.attrib['name']]=path
            sh.set('state','visible')
        else:
            book_sheets.remove(sh)
            files.pop(path,None);files.pop(relpath(path),None)
            for rel in list(rels):
                if rel.attrib['Id']==rid: rels.remove(rel)
    if set(selected)!=keep or not keep: raise PilotError('Fogli bug non corrispondenti al template')
    # Dependencies on excluded sheets cannot remain as broken formulas/validation lists.
    # Keep cached cell values. No extra lookup tab is added to the delivered workbook.
    defined=workbook.find(tag(M,'definedNames'))
    if defined is not None:
        for name in list(defined):
            text=name.text or ''
            if 'localSheetId' in name.attrib:
                previous=int(name.attrib['localSheetId'])
                kept=[n for n in selected if old_positions[n]==previous]
                if not kept: defined.remove(name);continue
                name.set('localSheetId',str(list(selected).index(kept[0])))
            if any(n not in keep and (n+'!' in text or "'"+n.replace("'","''")+"'!" in text) for n in old_positions):
                defined.remove(name)
    views=workbook.find(tag(M,'bookViews'))
    if views is not None:
        for view in views: view.set('activeTab','0');view.set('firstSheet','0')
    for rel in list(rels):
        if rel.attrib.get('Type','').endswith('/calcChain'):
            files.pop(part('xl/workbook.xml',rel.attrib['Target']),None);rels.remove(rel)
    rows_by_sheet=report_rows(run)
    types=ET.fromstring(files['[Content_Types].xml'])
    for override in list(types):
        if override.attrib.get('PartName','').lstrip('/') not in files and 'PartName' in override.attrib:
            types.remove(override)
    if not any(t.attrib.get('Extension')=='png' for t in types):
        ET.SubElement(types,tag(C,'Default'),{'Extension':'png','ContentType':'image/png'})
    # Bottom-to-top inserts leave earlier report-region coordinates valid.
    specs=sorted(contract['sheets'],key=lambda s:(s['name'],-s['data_start']))
    for sheet_index,spec in enumerate(specs):
        path=selected[spec['name']];root=ET.fromstring(files[path]);data=root.find(tag(M,'sheetData'))
        start,end=spec['data_start'],spec['data_end']; incoming=rows_by_sheet[report_id(spec)]
        span=spec.get('row_span',1)
        existing={int(r.attrib['r']):r for r in data}
        exemplars=[copy.deepcopy(existing.get(spec['style_row']+o,ET.Element(tag(M,'row')))) for o in range(span)]
        maximum=max(existing,default=end)
        count=max(1,len(incoming));last=start+count*span-1
        delta=max(0,last-end)
        for row in list(data):
            n=int(row.attrib['r'])
            if start<=n<=end: data.remove(row)
        # Keep/repeat merged cells belonging to each record, and shift the footer intact.
        merged=root.find(tag(M,'mergeCells'))
        record_merges=[]
        if merged is not None:
            for region in list(merged):
                left,top,right,bottom=range_boundaries(region.attrib['ref'])
                if bottom>=start and top<=end:
                    if top<start or bottom>end or (top-start)//span!=(bottom-start)//span:
                        raise PilotError('Celle unite attraversano il confine fra due difetti')
                    if spec['style_row']<=top<=bottom<spec['style_row']+span:
                        record_merges.append((left,top-spec['style_row'],right,bottom-spec['style_row']))
                    merged.remove(region)
        shift_rows(root,end,delta)
        if merged is not None:
            for index in range(count):
                for left,top,right,bottom in record_merges:
                    ET.SubElement(merged,tag(M,'mergeCell'),{'ref':f'{get_column_letter(left)}{start+index*span+top}:{get_column_letter(right)}{start+index*span+bottom}'})
            merged.set('count',str(len(merged)))
        drawings=root.find(tag(M,'drawing'))
        sheet_rels=ET.fromstring(files[relpath(path)]) if relpath(path) in files else ET.Element(tag(P,'Relationships'))
        if drawings is not None:
            drawing_rid=drawings.attrib[tag(R,'id')]
            relation=next(r for r in sheet_rels if r.attrib['Id']==drawing_rid)
            drawing_path=part(path,relation.attrib['Target'])
            drawing=ET.fromstring(files[drawing_path])
            drawing_rels=ET.fromstring(files[relpath(drawing_path)]) if relpath(drawing_path) in files else ET.Element(tag(P,'Relationships'))
            for anchor in list(drawing):
                marker=anchor.find(tag(D,'from'))
                number=marker.findtext(tag(D,'row')) if marker is not None else None
                if number is not None and start<=int(number)+1<=end: drawing.remove(anchor)
                else:
                    for marker in ('from','to'):
                        value=anchor.find(tag(D,marker)+'/'+tag(D,'row'))
                        if value is not None and int(value.text)+1>end:value.text=str(int(value.text)+delta)
        else:
            drawing_path=f'xl/drawings/lqa-{sheet_index}.xml'
            drawing=ET.Element(tag(D,'wsDr'));drawing_rels=ET.Element(tag(P,'Relationships'))
            drawing_rid='rIdLqaPictures'
            while any(r.attrib['Id']==drawing_rid for r in sheet_rels): drawing_rid+='X'
            ET.SubElement(sheet_rels,tag(P,'Relationship'),{'Id':drawing_rid,'Type':R+'/drawing','Target':posixpath.relpath(drawing_path,posixpath.dirname(path))})
            # drawing follows dataValidation/page setup but precedes tableParts/extLst.
            node=ET.Element(tag(M,'drawing'),{tag(R,'id'):drawing_rid})
            index=next((i for i,n in enumerate(root) if n.tag in {tag(M,'tableParts'),tag(M,'extLst')}),len(root))
            root.insert(index,node)
            ET.SubElement(types,tag(C,'Override'),{'PartName':'/'+drawing_path,'ContentType':'application/vnd.openxmlformats-officedocument.drawing+xml'})
        for index,item in enumerate(incoming):
            base=start+index*span;record=[];values=values_for_cells(item,spec)
            for offset,exemplar in enumerate(exemplars):
                n=base+offset;row=copy.deepcopy(exemplar);row.set('r',str(n));row.attrib.pop('spans',None)
                cells={re.sub(r'\d','',c.attrib['r']):c for c in row}
                for letter,c in cells.items():c.set('r',letter+str(n))
                for mapping in spec['columns']:
                    if mapping.get('row_offset',0)!=offset:continue
                    field=mapping['field'];letter=get_column_letter(mapping['column']);c=cells.get(letter)
                    if c is None:c=ET.SubElement(row,tag(M,'c'),{'r':letter+str(n)});cells[letter]=c
                    value=mapping.get('literal','') if field=='literal' and item['finding'] else values.get(field,'')
                    set_text(c,value)
                row[:]=sorted(list(row),key=lambda c:column_index_from_string(re.sub(r'\d','',c.attrib['r'])))
                data.append(row);record.append(row)
            if item['finding']:
                f=item['finding'];ev=run['evidence'][f['evidence_id']]
                marked=folder/'evidence'/(f['id']+'-annotated.png');annotate(folder/ev['path'],marked,f['bbox'])
                picture=next((c for c in spec['columns'] if c['field']=='screenshot'),None)
                shared=picture is None
                if shared:picture=next(c for c in spec['columns'] if c['field'] in {'description','comment','observed','fix'})
                column=picture['column'];offset=picture.get('row_offset',0);row=record[offset];n=base+offset
                height=min(409.5,max(float(row.attrib.get('ht','0')),409.5 if shared else 300));row.set('ht',str(height));row.set('customHeight','1')
                width=140
                for col in root.findall(tag(M,'cols')+'/'+tag(M,'col')):
                    if int(col.attrib['min'])<=column<=int(col.attrib['max']): width=float(col.attrib.get('width','20'))*7
                text_margin=0
                if shared:
                    chars=max(8,int(width/7))
                    lines=sum(max(1,math.ceil(len(line)/chars)) for line in values.get(picture['field'],'').splitlines())
                    text_margin=max(100,lines*16+12)
                    if text_margin>=height*4/3-40:
                        raise PilotError('Il testo e lo screenshot non entrano nella cella condivisa del report: serve una cella screenshot dedicata o più spazio nel formato cliente')
                with Image.open(marked) as im: w,h=im.size
                scale=min(max(12,width-8)/w,max(12,height*4/3-8-text_margin)/h)
                media=f'xl/media/lqa-{sheet_index}-{index}.png';files[media]=marked.read_bytes()
                rid='rIdLqa'+str(index)
                while any(r.attrib['Id']==rid for r in drawing_rels): rid+='X'
                ET.SubElement(drawing_rels,tag(P,'Relationship'),{'Id':rid,'Type':R+'/image','Target':posixpath.relpath(media,posixpath.dirname(drawing_path))})
                anchor=ET.SubElement(drawing,tag(D,'oneCellAnchor'));point=ET.SubElement(anchor,tag(D,'from'))
                for k,v in [('col',column-1),('colOff',38100),('row',n-1),('rowOff',38100+text_margin*9525)]: ET.SubElement(point,tag(D,k)).text=str(v)
                ET.SubElement(anchor,tag(D,'ext'),{'cx':str(round(w*scale*9525)),'cy':str(round(h*scale*9525))})
                pic=ET.SubElement(anchor,tag(D,'pic'));nv=ET.SubElement(pic,tag(D,'nvPicPr'))
                picture_id=1+max((int(e.attrib.get('id','0')) for e in drawing.iter(tag(D,'cNvPr'))),default=0)
                ET.SubElement(nv,tag(D,'cNvPr'),{'id':str(picture_id),'name':f['id']})
                ET.SubElement(nv,tag(D,'cNvPicPr'))
                fill=ET.SubElement(pic,tag(D,'blipFill'));ET.SubElement(fill,tag(A,'blip'),{tag(R,'embed'):rid})
                ET.SubElement(ET.SubElement(fill,tag(A,'stretch')),tag(A,'fillRect'))
                shape=ET.SubElement(pic,tag(D,'spPr'));ET.SubElement(ET.SubElement(shape,tag(A,'prstGeom'),{'prst':'rect'}),tag(A,'avLst'))
                ET.SubElement(anchor,tag(D,'clientData'))
        data[:]=sorted(list(data),key=lambda r:int(r.attrib['r']))
        for cell in root.iter(tag(M,'c')):
            formula=cell.find(tag(M,'f'))
            if formula is not None:
                if cell.find(tag(M,'v')) is None: raise PilotError('Formula del template senza valore salvato')
                cell.remove(formula)
        # Drop validations that depend on excluded worksheets/names; visual formatting is preserved.
        validations=root.find(tag(M,'dataValidations'))
        if validations is not None:
            for validation in list(validations):
                f=validation.findtext(tag(M,'formula1'),'')
                if f and not f.startswith('"'): validations.remove(validation)
            validations.set('count',str(len(validations)))
        dimension=root.find(tag(M,'dimension'))
        if dimension is not None:
            old_right=range_boundaries(dimension.attrib.get('ref','A1'))[2]
            dimension.set('ref',f"A1:{get_column_letter(max(old_right,max(c['column'] for c in spec['columns'])))}{max(maximum+delta,last)}")
        auto=root.find(tag(M,'autoFilter'))
        if auto is not None and range_boundaries(auto.attrib['ref'])[1]==spec['header_row']:
            auto.set('ref',f"A{spec['header_row']}:{get_column_letter(max(c['column'] for c in spec['columns']))}{last}")
        for table in root.findall(tag(M,'tableParts')+'/'+tag(M,'tablePart')):
            rel=next(r for r in sheet_rels if r.attrib['Id']==table.attrib[tag(R,'id')])
            table_path=part(path,rel.attrib['Target']);table_root=ET.fromstring(files[table_path])
            original=table_root.attrib['ref'];a,b=original.split(':')
            if int(re.search(r'\d+',a)[0])==spec['header_row']:
                table_root.set('ref',a+':'+re.sub(r'\d+','',b)+str(last))
                filt=table_root.find(tag(M,'autoFilter'))
                if filt is not None: filt.set('ref',table_root.attrib['ref'])
                files[table_path]=xml(table_root,files[table_path])
        files[path]=xml(root,files[path]);files[relpath(path)]=xml(sheet_rels)
        files[drawing_path]=xml(drawing,files.get(drawing_path));files[relpath(drawing_path)]=xml(drawing_rels)
    files['xl/workbook.xml']=xml(workbook,files['xl/workbook.xml']);files['xl/_rels/workbook.xml.rels']=xml(rels);files['[Content_Types].xml']=xml(types)
    target=folder/'report.xlsx';staging=folder/'report.pending.xlsx'
    files.save(staging)
    staging.replace(target)
    return target
