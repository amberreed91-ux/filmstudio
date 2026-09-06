import ast, os, re, sys, json, hashlib
from collections import defaultdict, Counter

ROOT = sys.argv[1]
MARKERS = re.compile(r'\b(TODO|FIXME|XXX|HACK|placeholder|not implemented|notimplemented|stub|mock(?!ing)|for now|temporary|hardcoded|dummy|fake)\b', re.I)

py_files=[]
for dp,dn,fn in os.walk(ROOT):
    if '__pycache__' in dp: continue
    for f in fn:
        if f.endswith('.py') and not f.endswith('.bak'):
            py_files.append(os.path.join(dp,f))

stubs=[]; markers=[]; big_files=[]; big_funcs=[]; dup=defaultdict(list)
defined=defaultdict(list)   # name -> [file]
used=Counter()
total_loc=0

def body_wo_doc(node):
    b=node.body
    if b and isinstance(b[0],ast.Expr) and isinstance(getattr(b[0],'value',None),(ast.Constant,)) and isinstance(b[0].value.value,str):
        b=b[1:]
    return b

for path in py_files:
    rel=os.path.relpath(path,ROOT)
    try:
        src=open(path,encoding='utf-8',errors='replace').read()
    except Exception: continue
    loc=src.count('\n')+1; total_loc+=loc
    if loc>=800: big_files.append((rel,loc))
    for i,line in enumerate(src.splitlines(),1):
        if MARKERS.search(line) and not line.strip().startswith(('import','from')):
            markers.append((rel,i,line.strip()[:120]))
    for tok in re.findall(r'[A-Za-z_][A-Za-z0-9_]*',src):
        used[tok]+=1
    try: tree=ast.parse(src)
    except Exception: continue
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            b=body_wo_doc(node)
            flen=(getattr(node,'end_lineno',node.lineno) or node.lineno)-node.lineno
            if flen>=150: big_funcs.append((rel,node.name,flen))
            # stub?
            reason=None
            if len(b)==0: reason='empty'
            elif len(b)==1:
                s=b[0]
                if isinstance(s,ast.Pass): reason='pass-only'
                elif isinstance(s,ast.Expr) and isinstance(getattr(s,'value',None),ast.Constant) and s.value.value is Ellipsis: reason='...-only'
                elif isinstance(s,ast.Raise) and 'NotImplemented' in ast.dump(s): reason='raise NotImplementedError'
                elif isinstance(s,ast.Return) and (s.value is None or isinstance(s.value,ast.Constant)): reason='returns constant only'
            if reason and not node.name.startswith('__'):
                stubs.append((rel,node.name,node.lineno,reason))
            # dup body signature (>=5 stmts)
            if len(b)>=5:
                try: sig=hashlib.md5(ast.dump(ast.Module(body=b,type_ignores=[])).encode()).hexdigest()
                except Exception: sig=None
                if sig: dup[sig].append(f"{rel}:{node.lineno} {node.name}()")
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            defined[node.name].append(rel)

# unused heuristic: defined once, name used <=1 time total (the def itself), not dunder/handler
unused=[]
for name,files in defined.items():
    if name.startswith('_') or name.startswith('test_'): continue
    if used[name]<=1 and len(files)==1:
        unused.append((files[0],name))

dupgroups=[(len(v),v) for k,v in dup.items() if len(v)>1]
dupgroups.sort(reverse=True)

print(json.dumps({
 "py_files": len(py_files),
 "total_loc": total_loc,
 "stub_count": len(stubs),
 "stubs": stubs[:80],
 "marker_count": len(markers),
 "markers_sample": markers[:60],
 "big_files": sorted(big_files,key=lambda x:-x[1])[:25],
 "big_funcs": sorted(big_funcs,key=lambda x:-x[2])[:25],
 "dup_body_groups": len(dupgroups),
 "dup_top": [g[1] for g in dupgroups[:15]],
 "unused_heuristic_count": len(unused),
 "unused_sample": unused[:60],
}, indent=1))
