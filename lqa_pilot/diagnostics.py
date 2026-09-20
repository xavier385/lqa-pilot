"""Bounded local diagnostics; no prompts, workbook contents or auth files."""
import json
import re
import threading
from pathlib import Path
from .util import now, read_json


def redact(value):
    text=str(value).replace(str(Path.home()),'<USER>').replace(Path.home().as_posix(),'<USER>')
    text=re.sub(r'(?i)Bearer\s+\S+', 'Bearer <REDACTED>',text)
    text=re.sub(r'(?i)((?:access_token|refresh_token|api_key|password|authorization)["\s]*[:=]\s*)[^\s,;]+',r'\1<REDACTED>',text)
    text=re.sub(r'\bsk-[A-Za-z0-9_-]+','<REDACTED>',text)
    return text


class DiagnosticLog:
    def __init__(self,folder):
        self.path=Path(folder)/'diagnostics.log';self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()

    def write(self,event,**details):
        line=redact(json.dumps({'time':now(),'event':event,**details},ensure_ascii=False,default=str))
        with self.lock:
            if self.path.exists() and self.path.stat().st_size>512*1024:
                self.path.replace(self.path.with_suffix('.previous.log'))
            with self.path.open('a',encoding='utf-8') as stream: stream.write(line[:16000]+'\n')

    def read(self):
        with self.lock:
            text=self.path.read_text(encoding='utf-8') if self.path.exists() else 'Nessun evento diagnostico.'
        return redact(text[-100000:])


def usage_totals(folder,attempted=0):
    groups={name:{'input_tokens':0,'cached_input_tokens':0,'output_tokens':0,'reported_calls':0} for name in ('planning','testing')}
    found=0
    for group,relative in (('planning','project/planning'),('testing','run/model')):
        for path in (Path(folder)/relative).glob('*.meta.json'):
            try: usage=read_json(path).get('usage',{})
            except (OSError,ValueError): continue
            found+=1
            if not isinstance(usage,dict): continue
            if not all(type(usage.get(k)) is int and usage[k]>=0 for k in ('input_tokens','output_tokens')): continue
            groups[group]['reported_calls']+=1
            for key in ('input_tokens','cached_input_tokens','output_tokens'):
                value=usage.get(key,0)
                if type(value) is int and value>=0: groups[group][key]+=value
    result={key:sum(group[key] for group in groups.values()) for key in groups['planning']}
    result['total_tokens']=result['input_tokens']+result['output_tokens']  # Cached input is already included.
    result['unreported_calls']=max(attempted,found)-result['reported_calls']
    result['groups']=groups
    return result
