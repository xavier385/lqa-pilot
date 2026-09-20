import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
let source=path.join(root,'../lqa_pilot/web');
try{await fs.access(source);}catch{source=path.join(root,'site');}
await fs.mkdir(path.join(root,'public'),{recursive:true});
for(const file of ['index.html','app.js','style.css'])await fs.copyFile(path.join(source,file),path.join(root,'public',file));
await fs.mkdir(path.join(root,'public/downloads'),{recursive:true});
try{await fs.copyFile(path.join(root,'downloads/LQA-Pilot-Windows.zip'),path.join(root,'public/downloads/LQA-Pilot-Windows.zip'));}catch(e){if(e.code!=='ENOENT')throw e;}
console.log('Static web app built. No database, cloud GPT calls or paid server functions.');
