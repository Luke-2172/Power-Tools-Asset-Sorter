"""Threaded Tk UI. All widget access occurs on the UI thread."""
import os, queue, threading
from pathlib import Path
from collections import Counter
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import engine
from safe_io import Cancelled

def launch():
    root=tk.Tk();root.title('FNV Asset Sorter 1.0');root.geometry('980x780');root.minsize(800,650)
    root.option_add('*Font','{Segoe UI} 10')
    frame=ttk.Frame(root,padding=18);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='FNV Asset Sorter',font=('Segoe UI',22,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Find required assets for an ESP/ESM • Copy files safely • Leave originals untouched').pack(anchor='w',pady=(3,14))
    form=ttk.Frame(frame);form.pack(fill='x');form.columnconfigure(1,weight=1)
    variables={k:tk.StringVar() for k in ('plugin','source','output','game')}; controls=[]
    def browse(key):
        value=filedialog.askopenfilename(title='Select Fallout New Vegas plugin',filetypes=[('FNV plugins','*.esp *.esm')]) if key=='plugin' else filedialog.askdirectory(title={'source':'Input folder containing Meshes / Textures / Sound','output':'Choose an empty output folder','game':'Fallout New Vegas installation or Data folder'}[key],mustexist=key!='output')
        if value:
            variables[key].set(value)
            if key=='source' and not variables['output'].get(): variables['output'].set(str(Path(value).parent/(Path(value).name+' - sorted')))
    for row,(key,label) in enumerate([('plugin','ESP / ESM'),('source','Input assets'),('output','Output folder'),('game','Game / Data folder')]):
        ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=(0,10),pady=5)
        e=ttk.Entry(form,textvariable=variables[key]);e.grid(row=row,column=1,sticky='ew');controls.append(e)
        b=ttk.Button(form,text='Browse…',command=lambda k=key:browse(k));b.grid(row=row,column=2,padx=(8,0));controls.append(b)
    ttk.Label(frame,text='Input must contain asset folders. Output uses required/, optional not required/, and reports.').pack(anchor='w',pady=(7,8))
    opts=ttk.LabelFrame(frame,text='Sorting options',padding=10);opts.pack(fill='x')
    settings={key:tk.BooleanVar(value=default) for key,default in [('exclude_vanilla',True),('conservative',True),('masters',True),('copy_unused',False)]}
    for key,label in [('exclude_vanilla','Exclude byte-identical vanilla textures (requires official game archives)'),('conservative','Keep uncertain assets and modified vanilla replacers (recommended)'),('masters','Scan master plugins too (conservative; searches plugin folder and Game/Data)'),('copy_unused','Also copy unused / vanilla files into “not required”')]:
        c=ttk.Checkbutton(opts,text=label,variable=settings[key]);c.pack(anchor='w');controls.append(c)
    bar=ttk.Frame(frame);bar.pack(fill='x',pady=12)
    events=queue.Queue(maxsize=300);stop=threading.Event();state={'busy':False,'plan':None}
    status=tk.StringVar(value='Choose your plugin and folders, then preview or sort.')
    def put(kind,value):
        if kind=='log':
            try: events.put_nowait((kind,value))
            except queue.Full: pass
        else: events.put((kind,value))
    def run(copy):
        values={k:v.get().strip() for k,v in variables.items()}
        if not all(values[k] for k in ('plugin','source','output')): messagebox.showerror('Missing selection','Choose the plugin, input assets and output folder.');return
        options={k:v.get() for k,v in settings.items()};state['busy']=True;stop.clear()
        for c in controls: c.configure(state='disabled')
        cancel.configure(state='normal');progress.start();text.delete('1.0','end');status.set('Scanning…')
        def worker():
            try:
                plan=engine.analyze(**values,**{k:v for k,v in options.items() if k!='copy_unused'},stop=stop,log=lambda s:put('log',s))
                counts=Counter(r[2] for r in plan['rows']);put('log','Scan totals: '+str(dict(counts)))
                for warning in plan['warnings']:put('log','REVIEW: '+warning)
                if copy:
                    out=engine.export(plan,options['copy_unused'],stop,lambda s:put('log',s));put('done',(plan,'Finished — '+str(out)))
                else:put('done',(plan,'Preview complete — no files written.'))
            except Cancelled as exc:put('error',('Cancelled',str(exc)))
            except Exception as exc:put('error',('Stopped',str(exc)+'\nOriginal files were not modified. If an output folder contains INCOMPLETE.txt, do not use it.'))
        threading.Thread(target=worker,daemon=True).start()
    for label,command in [('Preview',lambda:run(False)),('Sort / copy required',lambda:run(True))]:
        b=ttk.Button(bar,text=label,command=command);b.pack(side='left',padx=(0,8));controls.append(b)
    cancel=ttk.Button(bar,text='Cancel',state='disabled',command=lambda:(stop.set(),status.set('Cancelling after current operation…')));cancel.pack(side='left')
    def open_output():
        p=Path(variables['output'].get())
        if p.is_dir() and os.name=='nt':os.startfile(p)
        else:messagebox.showinfo('Output folder','The output folder has not been created yet.')
    helptext='FNV Asset Sorter 1.0\n\nWindows 10/11 x64. Python is bundled. No internet or administrator access needed.\n\n1. Select an ESP/ESM and an input folder containing Meshes, Textures, Sound, etc.\n2. Choose a new/empty output folder outside the input and game Data folders.\n3. Select Game/Data to exclude byte-identical official textures. Modified replacements are kept.\n4. Preview, then Sort / copy required. Install/test the contents of required/, not the reports.\n\nMaster scanning reads whole master plugins conservatively, so it may keep extra files. Missing masters are reported. Only official mesh/texture BSAs are indexed; custom BSA assets must be extracted into the input beforehand. The plugin itself is not copied unless already in the input.\n\nNIF references and shader companions are followed. This is a static scan, not a complete load-order resolver. Dynamic scripts, generated voice/FaceGen/LOD and inherited references may need manual review. Keep originals until tested in game.\n\nPreview displays up to 2,000 files; exported CSV reports cover all input files. Cancellation may leave INCOMPLETE.txt: do not use that partial output. Choose a fresh output folder to retry.\n\nSafety limits: plugins up to 1 GiB; each decoded record, mesh or compared texture up to 256 MiB. Large jobs can use several GiB of RAM.\n\nLinux engine tests passed; Windows GUI and in-game behavior have not been tested.'
    ttk.Button(bar,text='Help',command=lambda:messagebox.showinfo('FNV Asset Sorter — Help',helptext)).pack(side='right',padx=8)
    b=ttk.Button(bar,text='Open output',command=open_output);b.pack(side='right');controls.append(b)
    ttk.Label(frame,textvariable=status,wraplength=900).pack(anchor='w')
    progress=ttk.Progressbar(frame,mode='indeterminate');progress.pack(fill='x',pady=7)
    notebook=ttk.Notebook(frame);notebook.pack(fill='both',expand=True)
    preview=ttk.Frame(notebook);activity=ttk.Frame(notebook);notebook.add(preview,text='Preview');notebook.add(activity,text='Activity')
    tree=ttk.Treeview(preview,columns=('path','classification','reason'),show='headings')
    for col,width in [('path',360),('classification',110),('reason',370)]:tree.heading(col,text=col.title());tree.column(col,width=width)
    ys=ttk.Scrollbar(preview,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=ys.set);ys.pack(side='right',fill='y');tree.pack(fill='both',expand=True)
    text=tk.Text(activity,wrap='word',height=8);ts=ttk.Scrollbar(activity,command=text.yview);text.configure(yscrollcommand=ts.set);ts.pack(side='right',fill='y');text.pack(fill='both',expand=True)
    ttk.Label(frame,text='Static scan: dynamic script paths and generated assets can need review. Keep originals and test in game.',wraplength=920).pack(anchor='w',pady=(8,0))
    def unlock():
        state['busy']=False;progress.stop();cancel.configure(state='disabled')
        for c in controls:c.configure(state='normal')
    def poll():
        for _ in range(100):
            try:kind,value=events.get_nowait()
            except queue.Empty:break
            if kind=='log':
                text.insert('end',value+'\n');text.see('end');status.set(value)
                if int(text.index('end-1c').split('.')[0])>600:text.delete('1.0','101.0')
            elif kind=='done':
                plan,message=value;state['plan']=plan;tree.delete(*tree.get_children())
                for r in plan['rows'][:2000]:tree.insert('', 'end', values=(str(r[1]),r[2],r[3]))
                counts=Counter(r[2] for r in plan['rows']);status.set(message+'  '+str(dict(counts))+' — '+str(len(plan['warnings']))+' review notes (Activity tab)'+(' (Preview shows first 2,000 files)' if len(plan['rows'])>2000 else ''))
                unlock();notebook.select(preview)
            else:
                unlock();status.set(value[0]);messagebox.showerror(*value)
        root.after(80,poll)
    def close():
        if state['busy']:stop.set();status.set('Cancelling… Wait for the current operation, then close the window.')
        else:root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);root.after(80,poll);root.mainloop()
