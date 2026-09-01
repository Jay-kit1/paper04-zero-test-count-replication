#!/usr/bin/env python3
"""Independent compact recomputation of all exact consequence fractions."""

from __future__ import annotations

import argparse, csv, hashlib, json, math
from collections import Counter, defaultdict
from fractions import Fraction as F
from pathlib import Path

POS = "SOURCE_SUPPORTED_TEST_PRESENCE"
UNK = "SOURCE_EVIDENCE_UNRESOLVED"
NEG = "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED"
ORDER = ["Bukkit","CoreNLP","DiskLruCache","alluxio","android-volley","ansj_seg","graylog2-server","guava","java-design-patterns","javaee7-samples","javapoet","nanohttpd","presto","webmagic"]


def lines(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def box(x):
    return None if x is None else {"fraction": str(x), "decimal": f"{float(x):.12f}"}


def hg_interval(N, n, observed):
    choose = math.comb
    denom, cutoff = choose(N, n), F(1, 560)
    ok = []
    for total in range(observed, N - (n - observed) + 1):
        def p(x):
            if x > total or n-x > N-total: return F(0)
            return F(choose(total,x)*choose(N-total,n-x), denom)
        left = sum((p(x) for x in range(observed+1)), F(0))
        right = sum((p(x) for x in range(observed,n+1)), F(0))
        if left >= cutoff and right >= cutoff: ok.append(total)
    if not ok: raise ValueError((N,n,observed))
    return F(min(ok)), F(max(ok))


def metric(C,K,A,T,S):
    D=F(K)+S
    if S<0 or D>C: raise ValueError((C,K,S))
    loT = F(K)*T/D if D else None
    hiT = (F(K)*T+S)/D if D else None
    return {"S":box(S),"expanded_positive_row_coverage":box(D/C),"candidate_exclusion_share":box(S/D if D else None),"all_commits_rate_envelope":{"lower":box(A),"upper":box(A+S/C)},"all_commits_maximum_upward_sensitivity":box(S/C),"positive_parsed_test_rate_envelope":{"lower":box(loT),"upper":box(hiT),"defined":bool(D)}}


def avg(xs):
    xs=[x for x in xs if x is not None]
    return (sum(xs,F(0))/len(xs),len(xs)) if xs else (None,0)


def aggregate(rows, key):
    pairs=[(r,r[key]) for r in rows]
    C=sum(r["C"] for r,_ in pairs); K=sum(r["K"] for r,_ in pairs); S=sum((s for _,s in pairs),F(0))
    A=sum((r["A"]*r["C"] for r,_ in pairs),F(0))/C
    T=sum((r["T"]*r["K"] for r,_ in pairs),F(0))/K if K else F(0)
    pooled={"C":C,"K":K,"S":box(S),"published_A":box(A),"published_T":box(T),**metric(C,K,A,T,S)}
    m=[metric(r["C"],r["K"],r["A"],r["T"],s) for r,s in pairs]
    raw={
      "additional_count":[s for _,s in pairs],
      "expanded_positive_row_coverage":[F(x["expanded_positive_row_coverage"]["fraction"]) for x in m],
      "candidate_exclusion_share":[F(x["candidate_exclusion_share"]["fraction"]) if x["candidate_exclusion_share"] else None for x in m],
      "all_commits_maximum_upward_sensitivity":[F(x["all_commits_maximum_upward_sensitivity"]["fraction"]) for x in m],
      "positive_parsed_test_rate_lower":[F(x["positive_parsed_test_rate_envelope"]["lower"]["fraction"]) if x["positive_parsed_test_rate_envelope"]["lower"] else None for x in m],
      "positive_parsed_test_rate_upper":[F(x["positive_parsed_test_rate_envelope"]["upper"]["fraction"]) if x["positive_parsed_test_rate_envelope"]["upper"] else None for x in m]}
    balanced={}
    for name,xs in raw.items():
        value,count=avg(xs); balanced[name]={"value":box(value),"contributing_projects":count}
    return {"project_balanced":balanced,"pooled_commit_weighted":pooled}


def exact_leaves(obj,prefix=""):
    out={}
    if isinstance(obj,dict):
        for k,v in obj.items():
            path=f"{prefix}/{k}"
            if k in {"fraction","defined","contributing_projects","C","K"}: out[path]=v
            out.update(exact_leaves(v,path))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): out.update(exact_leaves(v,f"{prefix}/{i}"))
    return out


def main():
    ap=argparse.ArgumentParser()
    for name in ("sample","labels","published_csv","primary","out"):
        ap.add_argument("--"+name.replace("_","-"),type=Path,required=True)
    a=ap.parse_args()
    sample=json.loads(a.sample.read_text())["selected"]
    label={(x["project"],x["snapshot_key"]):x["category"] for x in lines(a.labels)}
    grouped=defaultdict(list)
    for x in sample: grouped[x["project"]].append((x,label[(x["project"],x["snapshot_key"])]))
    pub={x["Project"]:x for x in csv.DictReader(a.published_csv.open(newline=""))}
    rows=[]; expected_projects=[]
    for project in ORDER:
        group=grouped[project]; c=Counter(y for _,y in group); first=group[0][0]
        N,n=int(first["N_j"]),int(first["n_j"]); s,u,z=c[POS],c[UNK],c[NEG]
        C,K=int(pub[project]["Total Commits"]),int(pub[project]["Test buildable commits"])
        A,T=F(pub[project]["TestabilityRate_A"]),F(pub[project]["TestabilityRate_T"])
        lci=hg_interval(N,n,s); uci=hg_interval(N,n,s+u)
        values={"plugin_L":F(N*s,n),"plugin_U":F(N*(s+u),n),"ci_L_lower":lci[0],"ci_L_upper":lci[1],"ci_U_lower":uci[0],"ci_U_upper":uci[1],"worst_L_lower":F(s),"worst_L_upper":F(N-n+s),"worst_U_lower":F(s+u),"worst_U_upper":F(N-z)}
        rows.append({"project":project,"C":C,"K":K,"N":N,"n":n,"s":s,"u":u,"z":z,"A":A,"T":T,**values})
        expected_projects.append({"project":project,"C":C,"K":K,"N":N,"n":n,"sample_supported":s,"sample_unresolved":u,"sample_negative":z,"published":{"TestabilityRate_A":box(A),"TestabilityRate_T":box(T)},"candidate_counts":{k:box(v) for k,v in values.items()},"scenarios":{k:metric(C,K,A,T,v) for k,v in values.items()}})
    design={"plugin_endpoints":{"L":aggregate(rows,"plugin_L"),"U":aggregate(rows,"plugin_U")},"interval_aggregates":{}}
    for family in ("ci_L","ci_U","worst_L","worst_U"):
        design["interval_aggregates"][family]={"lower":aggregate(rows,family+"_lower"),"upper":aggregate(rows,family+"_upper")}
    expected={"projects":expected_projects,"design":design}
    primary=json.loads(a.primary.read_text())
    observed={"projects":primary["projects"],"design":{"plugin_endpoints":primary["design"]["plugin_endpoints"],"interval_aggregates":primary["design"]["interval_aggregates"]}}
    e,o=exact_leaves(expected),exact_leaves(observed)
    mismatches=[]
    for key in sorted(set(e)|set(o)):
        if e.get(key,"<MISSING>") != o.get(key,"<MISSING>"):
            mismatches.append({"path":key,"expected":e.get(key,"<MISSING>"),"observed":o.get(key,"<MISSING>")})
    category_ok=[x["project"] for x in primary["projects"]]==ORDER and primary["scope"]=={"projects":14,"collector_zero_frame_rows":1114,"sample_units":109}
    status="PASS" if not mismatches and category_ok else "FAIL"
    canonical=json.dumps(e,sort_keys=True,separators=(",",":")).encode()
    payload={"schema":"paper04-independent-compact-recompute/1.0","status":status,"exact_leaves_compared":len(e),"mismatches":mismatches,"categorical_and_scope_match":category_ok,"canonical_exact_leaf_sha256":hashlib.sha256(canonical).hexdigest(),"boundary":{"runtime_identified":False,"corrected_rate_claimed":False}}
    a.out.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    print(json.dumps(payload,indent=2))
    return 0 if status=="PASS" else 2

if __name__=="__main__": raise SystemExit(main())
