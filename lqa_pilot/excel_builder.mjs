import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const [payloadFile, output] = process.argv.slice(2);
const data = JSON.parse(await fs.readFile(payloadFile, 'utf8'));
const wb = Workbook.create();
const safe = v => typeof v==='string' && v.startsWith('=') ? "'"+v : v;
const col = n => {let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
for(const spec of data.sheets){
 const sh=wb.worksheets.add(spec.name), last=Math.max(1,spec.rows.length+1), end=col(spec.headers.length-1);
 sh.showGridLines=false;
 sh.getRange(`A1:${end}${last}`).format={font:{name:'Arial',size:11,color:'#17212B'},verticalAlignment:'top',wrapText:true};
 spec.widths.forEach((w,i)=>sh.getRange(`${col(i)}:${col(i)}`).format.columnWidthPx=w);
 sh.getRange(`A1:${end}1`).values=[spec.headers];
 sh.getRange(`A1:${end}1`).format={fill:'#E2EBF3',font:{bold:true},rowHeightPx:72};
 if(spec.rows.length){
  sh.getRange(`A2:${end}${last}`).values=spec.rows.map(r=>r.map(safe));
  sh.getRange(`A2:${end}${last}`).format.rowHeightPx=46;
  sh.tables.add(`A1:${end}${last}`,true,'BugList');
  sh.getRange(`A2:${end}${last}`).format.fill='#FFFFFF';
  sh.getRange(`P2:P${last}`).dataValidation={rule:{type:'list',values:data.review_options}};
 }
 for(const pic of spec.images){
  sh.getRange(`A${pic.row+1}:${end}${pic.row+1}`).format.rowHeightPx=532;
  const b=await fs.readFile(pic.path),w=b.readUInt32BE(16),h=b.readUInt32BE(20),f=Math.min(288/w,508/h);
  sh.images.add({dataUrl:`data:image/png;base64,${b.toString('base64')}`,anchor:{from:{row:pic.row,col:pic.column,rowOffsetPx:8,colOffsetPx:8},extent:{widthPx:w*f,heightPx:h*f}}});
 }
 sh.freezePanes.freezeRows(1);sh.freezePanes.freezeColumns(3);
 const preview=await wb.render({sheetName:spec.name,range:`A1:F${Math.min(last,2)}`,scale:1});
 await fs.writeFile(path.join(path.dirname(output),'preview-Bug-list.png'),new Uint8Array(await preview.arrayBuffer()));
}
wb.recalculate();
await(await SpreadsheetFile.exportXlsx(wb)).save(output);
console.log(output);
