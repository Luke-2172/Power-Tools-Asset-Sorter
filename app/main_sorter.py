"""Portable runtime entry point. Launched with isolated Python (-I)."""
from pathlib import Path
import os,sys,traceback,datetime
ROOT=Path(__file__).resolve().parent.parent
DLL_HANDLES=[]

def startup_error(exc):
    text=''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))
    logfile=None
    try:
        logs=Path(os.environ.get('LOCALAPPDATA',str(ROOT)))/'GoldIngotGames'/'FNV-Tools'/'Logs'
        from safe_io import reject_links,atomic_write
        reject_links(logs); logs.mkdir(parents=True,exist_ok=True)
        logfile=logs/('startup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.txt')
        atomic_write(logfile,data=text.encode('utf-8'))
    except Exception: pass
    message='The program could not start. Extract the complete ZIP into a local folder and try again.\n\n'+str(exc)
    if logfile: message+='\n\nDetails: '+str(logfile)
    if os.name=='nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,message,'FNV Tools - Startup error',0x10)
    else: print(message,file=sys.stderr)

try:
    sys.dont_write_bytecode=True
    if os.name=='nt':
        import ctypes
        ctypes.windll.kernel32.SetDefaultDllDirectories(0x1000)
        for folder in (ROOT/'runtime',ROOT/'runtime'/'DLLs'):
            DLL_HANDLES.append(os.add_dll_directory(str(folder)))
        os.environ['TCL_LIBRARY']=str(ROOT/'runtime'/'tcl'/'tcl8.6')
        os.environ['TK_LIBRARY']=str(ROOT/'runtime'/'tcl'/'tk8.6')
    from ui import launch
    launch()
except Exception as exc:
    startup_error(exc)
    sys.exit(1)
