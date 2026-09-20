"""Stream XLSX parts; inspect actual cells without expanding blank worksheet grids."""
import hashlib
import posixpath
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from openpyxl.utils.cell import range_boundaries, coordinate_from_string, column_index_from_string, get_column_letter
from .util import PilotError

M='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS={'m':M,'r':R}


def inspect_workbook(path, folder):
    path,folder=Path(path),Path(folder)
    try:
        with zipfile.ZipFile(path) as z:
            def relations(part):
                name=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
                if name not in z.namelist():return {}
                return {e.attrib['Id']:{**e.attrib,'part':e.attrib['Target'].lstrip('/') if e.attrib['Target'].startswith('/')
                    else posixpath.normpath(posixpath.join(posixpath.dirname(part),e.attrib['Target']))}
                    for e in ET.fromstring(z.read(name)) if e.attrib.get('TargetMode')!='External'}
            def texts(node):
                return ''.join(t.text or '' for t in node.iter('{'+M+'}t'))
            strings=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                with z.open('xl/sharedStrings.xml') as source:
                    for event,node in ET.iterparse(source,events=('end',)):
                        if node.tag=='{'+M+'}si':strings.append(texts(node));node.clear()
            workbook=ET.fromstring(z.read('xl/workbook.xml'));bookrels=relations('xl/workbook.xml')
            sheets=[];images=[]
            for index,sh in enumerate(workbook.find('m:sheets',NS)):
                part=bookrels[sh.attrib['{'+R+'}id']]['part'];rels=relations(part)
                rows={};merges=[];links=[];maxrow=0;maxcol=0
                with z.open(part) as source:
                    for event,node in ET.iterparse(source,events=('end',)):
                        kind=node.tag.rsplit('}',1)[-1]
                        if kind=='row':
                            n=int(node.attrib['r']);values={}
                            for c in node.findall('m:c',NS):
                                col,_=coordinate_from_string(c.attrib['r']);value=c.findtext('m:v',None,NS)
                                if c.attrib.get('t')=='s' and value is not None:value=strings[int(value)]
                                elif c.attrib.get('t')=='inlineStr':value=texts(c)
                                if value is None and c.find('m:f',NS) is not None:value='[Formula without cached result] '+c.findtext('m:f','',NS)
                                if value is not None:values[col]=str(value)
                                maxcol=max(maxcol,column_index_from_string(col))
                            if values:rows[n]={'row':n,'cells':values,'annotations':{}}
                            maxrow=max(maxrow,n);node.clear()
                        elif kind=='mergeCell':merges.append(node.attrib['ref'])
                        elif kind=='hyperlink':links.append(dict(node.attrib))
                relfile=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
                allrels={e.attrib['Id']:e.attrib for e in ET.fromstring(z.read(relfile))} if relfile in z.namelist() else {}
                for link in links:
                    col,n=coordinate_from_string(link['ref'].split(':')[0]);row=rows.setdefault(n,{'row':n,'cells':{},'annotations':{}})
                    row['annotations'][col]={'comment':'','hyperlink':allrels.get(link.get('{'+R+'}id'),{}).get('Target',link.get('location',''))}
                tables=[]
                for rel in rels.values():
                    if rel['Type'].endswith('/comments'):
                        for c in ET.fromstring(z.read(rel['part'])).findall('m:commentList/m:comment',NS):
                            col,n=coordinate_from_string(c.attrib['ref']);row=rows.setdefault(n,{'row':n,'cells':{},'annotations':{}})
                            row['annotations'].setdefault(col,{'hyperlink':''})['comment']=texts(c)
                    elif rel['Type'].endswith('/table'):
                        t=ET.fromstring(z.read(rel['part']));tables.append({'name':t.attrib.get('name',''),'range':t.attrib['ref']})
                    elif rel['Type'].endswith('/drawing'):
                        drawingrels=relations(rel['part'])
                        for anchor in ET.fromstring(z.read(rel['part'])):
                            start=next((c for c in anchor if c.tag.endswith('}from')),None)
                            n=1+int(next((c.text for c in start if c.tag.endswith('}row')),'0')) if start is not None else 1
                            for blip in anchor.iter():
                                rid=blip.attrib.get('{'+R+'}embed')
                                if rid not in drawingrels:continue
                                media=drawingrels[rid]['part'];suffix=Path(media).suffix.lower()
                                if suffix not in {'.png','.jpg','.jpeg','.webp','.gif','.bmp','.tif','.tiff'}:continue
                                target=folder/'references'/f'sheet-{index}-image-{len(images)}{suffix}';target.parent.mkdir(parents=True,exist_ok=True)
                                with z.open(media) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
                                images.append({'sheet':sh.attrib['name'],'row':n,'path':str(target.resolve())})
                                rows.setdefault(n,{'row':n,'cells':{'[image]':'Embedded reference image at this row'},'annotations':{}})
                regions=[(r,range_boundaries(r)) for r in merges]
                for n,row in rows.items():
                    row['merged_context']={r:rows.get(top,{}).get('cells',{}).get(get_column_letter(left),'')
                        for r,(left,top,right,bottom) in regions if top<=n<=bottom}
                sheets.append({'name':sh.attrib['name'],'max_row':max(maxrow,max(rows,default=0)),'max_column':maxcol,
                    'rows':[rows[n] for n in sorted(rows)],'merged_cells':merges,'visibility':sh.attrib.get('state','visible'),'tables':tables})
        with path.open('rb') as source:checksum=hashlib.file_digest(source,'sha256').hexdigest()
        return {'sheets':sheets,'images':images,'sha256':checksum}
    except (ValueError,KeyError,IndexError,ET.ParseError,zipfile.BadZipFile,OSError) as e:
        raise PilotError('Impossibile leggere il file XLSX: verificare formato, password e spazio disponibile. '+str(e)) from e


from .workbook_understanding import import_project
