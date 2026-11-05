"""Review operations: explicit routing, reproducible audit sampling and guarded reuse.

No label propagation. A reusable policy generates evidence-bound review drafts.
Evaluation reference labels live outside runtime queue data.
"""
import hashlib, json, random
from pathlib import Path
from engine import analyze, fingerprint

POLICY_VERSION='agency-review-1.0'
SUITE=Path(__file__).parent/'evaluation'/'boundary_cases.json'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def overlap(c):
    return bool(c.get('signals',{}).get('shared_operation') and c.get('signals',{}).get('same_app'))

def live_analysis(c):
    a=c.get('analysis')
    return a if a and a.get('fingerprint')==fingerprint(c) else analyze(c)

def eligibility(c):
    a=live_analysis(c); dims=a['dimensions']
    if not overlap(c):return False,'不属于共享操作与同 App 的模式'
    if dims['group']['value']=='conflict':return False,'控制关系材料冲突，需专家逐项核验'
    if dims['group']['value']!='unknown':return False,'已有独立控制关系证据，不能套用代理解释'
    if dims['agency']['value']!='yes':return False,'缺少覆盖本案且有效、已核对的代理授权'
    return True,'本案授权有效；控制关系未确认，可准备代理关系复核'

def descriptor(c):
    a=live_analysis(c); dims=a['dimensions']; context=c.get('graph_context',{})
    members=set(context.get('left_members',[c['a']])+context.get('right_members',[c['b']]))
    conflict=any(d['value']=='conflict' for d in dims.values())
    impact=len(members)
    if conflict:rank=0;route='专家核验';reason='存在相反材料，需判断有效版本'
    elif impact>=8:rank=1;route='专家核验';reason=f'候选边连接两组共 {impact} 个主体，错误关联影响较大'
    elif overlap(c) and eligibility(c)[0]:rank=2;route='模式复核';reason='代理授权可解释操作重合，可作为同类检查的代表'
    elif dims['group']['value'] in ('same','independent'):rank=3;route='常规复核';reason='已有直接控制关系材料，按引用核对'
    else:rank=4;route='补证优先';reason='现有材料不足，先取得关键证明'
    prepared=c.get('prepared')
    return {'id':c['id'],'title':c['title'],'region':c['region'],'status':c['status'],
        'route':route,'reason':reason,'rank':rank,'impact':impact,
        'overlap':overlap(c),'agency':dims['agency']['label'],'group':dims['group']['label'],
        'eligible':eligibility(c)[0],
        'prepared':bool(prepared and prepared['fingerprint']==fingerprint(c)),
        'upstream':c.get('upstream',{}),'source_count':a['source_count']}

def queue(cases, budget=4, seed='review-01'):
    pool=[c for c in cases if c.get('batch') and not c.get('hidden')]
    rows=[descriptor(c) for c in pool]
    candidates=sorted([r for r in rows if r['status'] not in ('已归档','待复核')],key=lambda r:(r['rank'],r['id']))
    budget=max(1,min(int(budget),len(candidates))) if candidates else 0
    # Reserve one seat for a reproducible random audit from the remaining pool.
    diverse=[];deferred=[];seen_pattern=False
    for row in candidates:
        if row['route']=='模式复核':
            if seen_pattern:deferred.append(row);continue
            seen_pattern=True
        diverse.append(row)
    priority=(diverse+deferred)[:max(0,budget-1)]
    rest=[r for r in candidates if r not in priority]
    audit=random.Random(str(seed)).choice(rest) if rest and budget else None
    selected=[dict(r,selection='优先核验') for r in priority]
    if audit:selected.append(dict(audit,selection='随机抽检',reason='从未入选优先队列的案例中随机抽取，检查盲区；原分流：'+audit['route']))
    cluster=[r for r in rows if r['overlap']]
    return {'rows':sorted(rows,key=lambda r:(r['rank'],r['id'])),'selected':selected,'seed':str(seed),'budget':budget,
        'total':len(rows),'open':len(candidates),'conflicts':sum(r['rank']==0 for r in rows),
        'cluster':cluster,'eligible':sum(r['eligible'] for r in cluster),
        'prepared':sum(r['prepared'] for r in rows),'archived':sum(c['archived'] for c in pool),
        'note':'排序是可解释的产品规则，不是模型置信度；抽检用于发现未优先处理的错误。'}

def source_valid(policy, cases):
    c=next((c for c in cases if c['id']==policy['source_id']),None)
    if not c or fingerprint(c)!=policy['source_fingerprint']:return False
    return any(r['id']==policy['source_review_id'] and r['status']=='approved' and 'agency' in r['selected'] for r in c['reviews'])

def preview(policy,cases):
    rows=[]
    for c in cases:
        if not c.get('batch') or c.get('hidden') or not overlap(c):continue
        ok,reason=eligibility(c)
        if c['id']==policy['source_id']:ok=False;reason='来源案例已复核，仅作为规则依据'
        elif c['status'] in ('已归档','待复核'):ok=False;reason='本案已有档案或待复核记录'
        elif c.get('prepared',{}).get('policy_id')==policy['id'] and c['prepared']['fingerprint']==fingerprint(c):ok=False;reason='已生成同版本复核草稿，无需重复'
        a=live_analysis(c)
        rows.append({'id':c['id'],'title':c['title'],'eligible':ok,'reason':reason,
            'refs':[x['material_id'] for x in a['dimensions']['agency']['claims']],
            'group':a['dimensions']['group']['label'],'agency':a['dimensions']['agency']['label'],
            'fingerprint':fingerprint(c)})
    return rows

def policy_hash(policy):
    return digest({k:policy[k] for k in ('id','source_id','source_review_id','source_fingerprint','version','name','rationale')})

def evaluate(policy):
    # Fixed independently specified boundary fixtures, never used for queue ranking.
    raw=SUITE.read_bytes(); suite=json.loads(raw); rows=[]
    for item in suite['cases']:
        c=item['input'];actual,reason=eligibility(c)
        naive=overlap(c)
        rows.append({'id':item['id'],'name':item['name'],'expected':item['eligible'],
            'actual':actual,'passed':actual==item['eligible'],'reason':reason,
            'baseline':naive,'baseline_passed':naive==item['eligible']})
    return {'suite_version':suite['version'],'dataset_sha256':hashlib.sha256(raw).hexdigest(),
        'policy_hash':policy_hash(policy),'policy_version':policy['version'],
        'total':len(rows),'passed':sum(r['passed'] for r in rows),
        'failed':sum(not r['passed'] for r in rows),'baseline_passed':sum(r['baseline_passed'] for r in rows),
        'rows':rows,'notice':'合成边界回归，只验证规则适用性；不是线上准确率、节省工时或召回率。'}

def evaluation_current(policy):
    e=policy.get('evaluation')
    return bool(e and e['policy_hash']==policy_hash(policy) and e['policy_version']==POLICY_VERSION
                and e['dataset_sha256']==hashlib.sha256(SUITE.read_bytes()).hexdigest()
                and e['total']>0 and e['failed']==0)

def make_draft(policy,c):
    ok,reason=eligibility(c)
    if not ok:raise ValueError(reason)
    a=live_analysis(c);claims=a['dimensions']['agency']['claims']
    refs='；'.join(x['material_id']+'：'+x['quote']+'（'+x['scope']+'）' for x in claims)
    return {'policy_id':policy['id'],'policy_name':policy['name'],'version':policy['version'],
        'fingerprint':fingerprint(c),'selected':['agency'],'refs':[x['material_id'] for x in claims],
        'rationale':'请核对本案代理授权：'+refs+'。本次仅提交代理关系，集团关系保持未确认；不将操作相似直接作为控制关系证明。',
        'source_case':policy['source_id'],'source_review':policy['source_review_id']}
