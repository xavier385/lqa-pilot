"""Loopback-only companion for the hosted UI. No cloud API keys or remote ADB."""
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
import traceback
import tempfile
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from .util import PilotError, read_json, write_json
from .diagnostics import DiagnosticLog, usage_totals, redact
from . import __version__

PORT=18766
WEB_ROOT=Path(__file__).parent/'web'
ACTIVE={'importing','running','stopping'}


class Jobs:
    def __init__(self,folder):
        self.folder=Path(folder).resolve();self.folder.mkdir(parents=True,exist_ok=True)
        self.log=DiagnosticLog(self.folder/'logs')
        self.log.write('companion.started',version=__version__)
        self.lock=threading.RLock();self.cancelled=threading.Event()
        self.current=None;self.thread=None
        latest=self.folder/'latest.json'
        if latest.is_file():
            self.current=read_json(latest)
            if self.current['status'] in ACTIVE:
                self.current.update(status='interrupted',message='Il componente locale è stato chiuso. Il lavoro non è completo.')
                self.save()

    def save(self):
        if self.current: write_json(self.folder/'latest.json',self.current)

    def update(self,**values):
        with self.lock:
            self.current.update(values);self.save()

    def public(self):
        with self.lock:
            if not self.current: return None
            state=dict(self.current)
        path=self.folder/state['id']/'run/run.json'
        attempted=0
        if path.is_file():
            try:
                run=read_json(path)
                state['progress']={'completed':sum(c.get('coverage')=='complete' for c in run['cases'].values()),
                    'total':len(run['project']['cases']),'calls':run['calls']}
                attempted=run['calls']
            except (OSError,ValueError): pass
        try: attempted+=read_json(self.folder/state['id']/'project/planning-progress.json')['calls']
        except (OSError,ValueError,KeyError): pass
        state['usage']=usage_totals(self.folder/state['id'],attempted)
        return state

    def submit(self,contents,filename,options):
        with self.lock:
            if self.current and self.current['status'] in ACTIVE: raise PilotError('Un progetto è già in esecuzione')
            if options.get('mode') not in {'full','fast','video'}: raise PilotError('Scegliere una modalità valida')
            if not options.get('language') or len(options['language'])>60: raise PilotError('Indicare la lingua da testare')
            if options.get('package') and not re.fullmatch(r'[A-Za-z][\w]*(?:\.[\w]+)+',options['package']):raise PilotError('Package Android non valido')
            if not options.get('package') and not str(options.get('game_name','')).strip():raise PilotError('Indicare il nome del gioco da aprire')
            limit=options.get('max_calls',100)
            if type(limit)!=int or not 10<=limit<=500: raise PilotError('Limite chiamate non valido')
            ident=uuid.uuid4().hex;folder=self.folder/ident;folder.mkdir()
            if isinstance(contents,Path):shutil.move(str(contents),folder/'input.xlsx')
            else:(folder/'input.xlsx').write_bytes(contents)
            self.current={'id':ident,'filename':filename,'status':'importing','mode':options['mode'],
                          'message':'Lettura del progetto Excel','downloads':[]}
            self.cancelled.clear();self.save()
            self.log.write('job.submitted',id=ident,mode=options['mode'])
            self.thread=threading.Thread(target=self.work,args=(folder,options),daemon=True);self.thread.start()
            return self.public()

    def work(self,folder,options):
        try:
            from .workbook_project import import_project
            from .project import load_project
            from .engine import Engine
            from .android import Android
            from .report import export
            project=import_project(folder/'input.xlsx',folder/'project',options,
                progress=lambda t:self.update(message=t),cancelled=self.cancelled.is_set)
            if self.cancelled.is_set(): raise PilotError('Lavoro interrotto')
            plan=load_project(project)
            summary=plan.get('import_summary')
            if not summary or not summary.get('ready'):raise PilotError('Analisi del progetto non completata: navigazione non avviata')
            self.update(import_summary=summary,message='Contesto e formato report verificati. Avvio del testing.')
            self.log.write('project.understood',**summary)
            engine=Engine(plan,folder/'run',driver=Android(plan['device'],diagnostics=self.log.write),diagnostics=self.log.write)
            self.update(status='running',message='Navigazione e raccolta delle prove')
            if self.cancelled.is_set(): (folder/'run/STOP').touch()
            state=engine.run(launch=True)
            if options['mode']=='video':
                downloads=[{'name':Path(c['video']['path']).name,'key':cid,'kind':'video',
                            'partial':c.get('coverage')!='complete'} for cid,c in state['cases'].items() if c.get('video',{}).get('path')]
            else:
                export(folder/'run')
                downloads=[{'name':'LQA-'+options['mode']+'.xlsx','key':'report','kind':'excel'}]
            complete=all(c.get('coverage')=='complete' for c in state['cases'].values())
            status='complete' if complete else 'partial'
            message='Risultato pronto per la revisione' if complete else 'Lavoro parziale: le sezioni non completate non sono Pass'
            self.update(status=status,message=message,downloads=downloads)
            self.log.write('job.finished',status=status)
        except (Exception,KeyboardInterrupt) as e:
            self.log.write('job.error',error=str(e),traceback=traceback.format_exc())
            self.update(status='interrupted' if self.cancelled.is_set() else 'error',message=redact(str(e))[:600])

    def stop(self):
        with self.lock:
            if not self.current or self.current['status'] not in ACTIVE: return
            self.cancelled.set()
            folder=self.folder/self.current['id']/'run'
            if folder.is_dir(): (folder/'STOP').touch()
            self.update(status='stopping',message='Arresto richiesto; salvo le prove già raccolte')

    def download(self,key):
        if not self.current: raise PilotError('Nessun risultato disponibile')
        item=next((d for d in self.current['downloads'] if d['key']==key),None)
        if not item: raise PilotError('Risultato non disponibile')
        folder=self.folder/self.current['id']/'run'
        path=folder/'report.xlsx' if key=='report' else folder/'videos'/(key+'.mp4')
        if not path.is_file(): raise PilotError('File non disponibile')
        return path,item['name']


class Companion:
    def __init__(self,folder,origin='',port=PORT):
        self.jobs=Jobs(folder);self.port=port
        self.origin=origin.rstrip('/')
        if self.origin and (urlsplit(self.origin).scheme!='https' or urlsplit(self.origin).path not in {'','/'}):
            raise PilotError('L’indirizzo della web app deve essere un’origine HTTPS, senza percorsi')
        self.code=secrets.token_hex(4).upper();self.token=None;self.session_origin=None
        self.failures=0;self.code_created=time.monotonic();self.auth_lock=threading.Lock()
        self.server=None
        self.device_config={'serial':'auto'}

    def detect(self,options):
        from .android import Android
        from .codex import Codex
        if self.jobs.current and self.jobs.current['status'] in ACTIVE:
            raise PilotError('Attendere la fine del lavoro prima di cambiare il collegamento Android')
        config={'serial':str(options.get('serial','')).strip() or 'auto'}
        if len(config['serial'])>120 or any(c.isspace() for c in config['serial']): raise PilotError('Serial Android non valido')
        port=str(options.get('port','')).strip()
        if port:
            if not port.isascii() or not port.isdecimal() or not 1<=int(port)<=65535: raise PilotError('Porta ADB non valida (1–65535)')
            config['endpoint']='127.0.0.1:'+str(int(port))
        self.device_config={'serial':'auto'}
        self.jobs.log.write('device.detect.begin',config=config)
        d=Android(config,diagnostics=self.jobs.log.write);d.connect();package=d.foreground()
        self.jobs.log.write('device.foreground',package=package)
        auth=Codex(self.jobs.folder/'auth-check').check_auth()
        self.device_config={**config,'serial':d.serial}
        self.jobs.log.write('device.detect.ready',serial=d.serial,package=package,authentication='ChatGPT')
        return {'package':package,'account':auth,'serial':d.serial}

    def allowed(self,origin):
        return bool(origin) and origin in {self.origin,f'http://127.0.0.1:{self.port}',f'http://localhost:{self.port}'}

    def pair(self,origin,code):
        with self.auth_lock:
            if not self.allowed(origin) or self.failures>=8 or time.monotonic()-self.code_created>900:
                raise PilotError('Collegamento scaduto: riaprire il componente locale')
            if not hmac.compare_digest(str(code),self.code):
                self.failures+=1;raise PilotError('Codice di collegamento non valido')
            self.token=secrets.token_urlsafe(32);self.session_origin=origin
            self.code=secrets.token_hex(4).upper();self.code_created=time.monotonic()
            return self.token

    def authorized(self,origin,header):
        return self.allowed(origin) and origin==self.session_origin and self.token and hmac.compare_digest(header,'Bearer '+self.token)

    def start(self):
        app=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_OPTIONS(self):
                if not self.valid_host() or not app.allowed(self.headers.get('Origin','')):
                    self.send_error(403);return
                self.send_response(204);self.cors();self.end_headers()

            def valid_host(self): return self.headers.get('Host','') in {f'127.0.0.1:{app.port}',f'localhost:{app.port}'}
            def cors(self):
                origin=self.headers.get('Origin','')
                if app.allowed(origin):
                    self.send_header('Access-Control-Allow-Origin',origin)
                    self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type, X-Filename, X-Options')
                    self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
                    self.send_header('Access-Control-Allow-Private-Network','true')
                    self.send_header('Vary','Origin')
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')

            def answer(self,data,status=200):
                body=json.dumps(data,ensure_ascii=False).encode('utf-8')
                self.send_response(status);self.cors();self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

            def body(self,limit=32768):
                try: count=int(self.headers.get('Content-Length','0'))
                except ValueError: raise PilotError('Dimensione richiesta non valida')
                if not 0<count<=limit: raise PilotError('Dimensione richiesta non valida o file troppo grande')
                self.connection.settimeout(30)
                value=self.rfile.read(count)
                if len(value)!=count: raise PilotError('Caricamento interrotto')
                return value

            def workbook_body(self):
                try:remaining=int(self.headers.get('Content-Length','0'))
                except ValueError:raise PilotError('Dimensione richiesta non valida')
                if remaining<=0:raise PilotError('File Excel vuoto')
                self.connection.settimeout(120)
                fd,name=tempfile.mkstemp(suffix='.xlsx',prefix='upload-',dir=app.jobs.folder)
                target=Path(name)
                try:
                    with os.fdopen(fd,'wb') as dst:
                        while remaining:
                            chunk=self.rfile.read(min(1024*1024,remaining))
                            if not chunk:raise PilotError('Caricamento interrotto')
                            dst.write(chunk);remaining-=len(chunk)
                    return target
                except BaseException:
                    target.unlink(missing_ok=True);raise

            def do_GET(self): self.route(False)
            def do_POST(self): self.route(True)
            def route(self,post):
                try:
                    if not self.valid_host(): self.send_error(403);return
                    route=urlsplit(self.path).path;origin=self.headers.get('Origin','')
                    if not origin and self.headers.get('Sec-Fetch-Site')=='same-origin':
                        origin='http://'+self.headers.get('Host','')
                    if not post and route in {'/','/index.html','/app.js','/style.css'}:
                        name='index.html' if route=='/' else route[1:]
                        data=(WEB_ROOT/name).read_bytes()
                        self.send_response(200);self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'application/javascript','css':'text/css'}[name.split('.')[-1]])
                        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data);return
                    if not app.allowed(origin): self.answer({'error':'Origine non autorizzata'},403);return
                    if post and route=='/pair':
                        self.answer({'token':app.pair(origin,json.loads(self.body()).get('code',''))});return
                    if not app.authorized(origin,self.headers.get('Authorization','')):
                        self.answer({'error':'Collega questo PC con il codice mostrato nel componente locale'},401);return
                    if not post and route=='/status': self.answer({'job':app.jobs.public(),'version':__version__});return
                    if not post and route=='/diagnostics':
                        self.answer({'log':app.jobs.log.read(),'version':__version__});return
                    if post and route=='/device':
                        options=json.loads(self.body()) if self.headers.get('Content-Length','0')!='0' else {}
                        if not isinstance(options,dict): raise PilotError('Opzioni collegamento non valide')
                        self.answer(app.detect(options));return
                    if post and route=='/jobs':
                        opts=json.loads(unquote(self.headers.get('X-Options','{}')))
                        opts['device']=dict(app.device_config)
                        filename=Path(unquote(self.headers.get('X-Filename','project.xlsx'))).name[:150]
                        if not filename.lower().endswith('.xlsx'): raise PilotError('Caricare un file .xlsx')
                        uploaded=self.workbook_body()
                        try:self.answer(app.jobs.submit(uploaded,filename,opts),202)
                        finally:uploaded.unlink(missing_ok=True)
                        return
                    if post and route=='/stop': app.jobs.stop();self.answer({'ok':True});return
                    if not post and route.startswith('/download/'):
                        path,name=app.jobs.download(route.rsplit('/',1)[-1])
                        self.send_response(200);self.cors()
                        self.send_header('Content-Type','video/mp4' if path.suffix=='.mp4' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                        self.send_header('Content-Length',str(path.stat().st_size));self.send_header('Content-Disposition','attachment; filename="'+name+'"')
                        self.end_headers()
                        with path.open('rb') as f:
                            while chunk:=f.read(1024*1024): self.wfile.write(chunk)
                        return
                    self.answer({'error':'Operazione non disponibile'},404)
                except Exception as e:
                    app.jobs.log.write('request.error',route=urlsplit(self.path).path,error=str(e),traceback=traceback.format_exc())
                    self.answer({'error':redact(str(e))[:600]},400)
        self.server=ThreadingHTTPServer(('127.0.0.1',self.port),Handler)
        self.port=self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        return self.server
