"""Small local companion window; operators never need a terminal."""
import os
import subprocess
import threading
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from pathlib import Path

from .util import read_json, write_json, PilotError
from .web_bridge import Companion, PORT


def main():
    if sys.stdout is None: sys.stdout=open(os.devnull,'w',encoding='utf-8')
    if sys.stderr is None: sys.stderr=open(os.devnull,'w',encoding='utf-8')
    if '--self-check' in sys.argv:
        from .web_bridge import WEB_ROOT
        from .util import executable
        assert (WEB_ROOT/'index.html').is_file()
        assert Path(executable('ffmpeg')).is_file()
        check=tk.Tk();check.withdraw();check.update();check.destroy()
        return
    root=tk.Tk();root.title('LQA Pilot · Collegamento PC');root.geometry('540x430');root.resizable(False,False)
    home=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'LQA Pilot';home.mkdir(parents=True,exist_ok=True)
    config_file=home/'web.json';config=read_json(config_file) if config_file.is_file() else {}
    bundled_origin=Path(sys.executable).parent/'web-origin.json' if getattr(sys,'frozen',False) else Path(__file__).parents[1]/'web-origin.json'
    if not config.get('origin') and bundled_origin.is_file(): config=read_json(bundled_origin)
    frame=ttk.Frame(root,padding=28);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='LQA Pilot',font=('Segoe UI',22,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Questo componente collega la web app al tuo MuMu.',wraplength=470).pack(anchor='w',pady=(6,20))
    ttk.Label(frame,text='Indirizzo della web app (HTTPS)').pack(anchor='w')
    origin=tk.StringVar(value=config.get('origin',''))
    entry=ttk.Entry(frame,textvariable=origin,width=64);entry.pack(fill='x',pady=6)
    state=tk.StringVar(value='Apri MuMu e collega questo PC. Il bot aprirà il gioco.')
    code=tk.StringVar(value='');companion=[None]
    def start():
        try:
            if companion[0] is None:
                app=Companion(home/'jobs',origin.get().strip());app.start();companion[0]=app
                write_json(config_file,{'origin':app.origin});entry.config(state='disabled')
            app=companion[0];code.set(app.code);state.set('Inserisci questo codice nella web app. Lascia aperta questa finestra.')
            webbrowser.open(app.origin or f'http://127.0.0.1:{PORT}')
        except (PilotError,OSError) as e: messagebox.showerror('Collegamento',str(e))
    def login():
        def work():
            try:
                from .codex import Codex
                c=Codex(home/'login')
                proc=subprocess.run([c.exe,'login'],env=c.environment(),capture_output=True,timeout=240,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                text='Accesso ChatGPT completato' if proc.returncode==0 else 'Accesso non completato. Verifica Codex e riprova.'
            except (PilotError,OSError,subprocess.TimeoutExpired) as e: text=str(e)
            root.after(0,lambda:state.set(text))
        state.set('Completa l’accesso nella pagina ChatGPT che si apre.');threading.Thread(target=work,daemon=True).start()
    ttk.Button(frame,text='Collega e apri la web app',command=start).pack(fill='x',pady=(12,8))
    ttk.Label(frame,textvariable=code,font=('Consolas',25,'bold')).pack(pady=4)
    ttk.Label(frame,textvariable=state,wraplength=470).pack(anchor='w',pady=6)
    ttk.Button(frame,text='Accedi con il mio account ChatGPT',command=login).pack(fill='x',pady=8)
    def closing():
        app=companion[0]
        if app and app.jobs.current and app.jobs.current['status'] in {'running','importing','stopping'}:
            app.jobs.stop();state.set('Arresto in corso. Attendi il salvataggio prima di chiudere.');return
        if app: app.server.shutdown()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',closing);root.mainloop()


if __name__=='__main__': main()
