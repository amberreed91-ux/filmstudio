import os,re,sys,json,hashlib
from collections import defaultdict,Counter
ROOT=sys.argv[1]
files=[]
for dp,dn,fn in os.walk(ROOT):
    if 'node_modules' in dp: continue
    for f in fn:
        if f.endswith(('.ts','.tsx')): files.append(os.path.join(dp,f))
MARK=re.compile(r'\b(TODO|FIXME|XXX|HACK|not implemented|placeholder|stub|for now|temporary|hardcoded|dummy)\b',re.I)
markers=[];big=[];anys=Counter();consolelogs=[];empties=[];dup=defaultdict(list);total=0
tests=0
for p in files:
    rel=os.path.relpath(p,ROOT)
    if re.search(r'\.test\.|\.spec\.',rel): tests+=1; continue
    try: src=open(p,encoding='utf-8',errors='replace').read()
    except: continue
    loc=src.count('\n')+1; total+=loc
    if loc>=700: big.append((rel,loc))
    for i,l in enumerate(src.splitlines(),1):
        if MARK.search(l) and not l.strip().startswith(('import','*','//')): pass
        if MARK.search(l): markers.append((rel,i,l.strip()[:110]))
        if re.search(r'\bconsole\.(log|debug)\(',l): consolelogs.append((rel,i))
    anys[rel]=len(re.findall(r':\s*any\b',src))
    empties+= [(rel,)] if re.search(r'=>\s*\{\s*\}',src) else []
    # crude dup: normalized 8-line windows
    lines=[re.sub(r'\s+','',x) for x in src.splitlines() if x.strip() and not x.strip().startswith('//')]
    for i in range(0,len(lines)-8):
        blk='\n'.join(lines[i:i+8])
        if len(blk)>120:
            dup[hashlib.md5(blk.encode()).hexdigest()].append(f"{rel}:{i+1}")
totany=sum(anys.values())
dupg=[(len(set(v)),list(dict.fromkeys(v))) for k,v in dup.items() if len(set(v))>1]
dupg.sort(reverse=True)
print(json.dumps({
 "ts_files":len(files),"test_files":tests,"app_loc":total,
 "marker_count":len(markers),"markers_sample":markers[:40],
 "console_logs":len(consolelogs),"console_sample":consolelogs[:15],
 "any_total":totany,"any_top":sorted(anys.items(),key=lambda x:-x[1])[:12],
 "big_files":sorted(big,key=lambda x:-x[1])[:20],
 "dup_block_groups":len(dupg),"dup_top":[g[1][:4] for g in dupg[:10]],
},indent=1))
