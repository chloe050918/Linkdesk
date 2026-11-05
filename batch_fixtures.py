"""Fictional incoming cases. No reference labels are stored in the work queue."""
from copy import deepcopy
from fixtures import material

BATCH_ID = 'nov-review-01'

def make_case(number, a, b, kind='overlap', agreement=False, group=None,
              expired=False, unverified=False, impact=2):
    cid=f'batch-{number:02d}'
    scope=f'2026 年第四季度，{a[:2]}品牌投放。'
    materials=[]
    if kind=='overlap':
        materials.append(material(cid+'-S','操作与推广对象记录','signal',
            f'涉及主体：{a}；{b}\n两家公司共享办公出口 IP，并推广同一 App。\n此行为也可由代运营服务产生。',
            '平台操作记录 · 虚构样例'))
    else:
        materials.append(material(cid+'-S','候选关系线索','signal',
            f'涉及主体：{a}；{b}\n主体名称或联系人出现交集，需要补充关系依据。',
            '候选关系队列 · 虚构样例'))
    if agreement:
        materials.append(material(cid+'-A','客户提供的投放授权','agreement',
            f'涉及主体：{a}；{b}\n{a}委托{b}执行广告投放。\n适用范围：{scope}\n本文件不构成股权控制或预算最终审批权证明。',
            '客户资料负责人 · 虚构签署原件',verified=not unverified,
            expires='2026-09-30' if expired else '2026-12-31'))
    if group in ('same','conflict'):
        materials.append(material(cid+'-G','主体控制关系摘录','registry',
            f'涉及主体：{a}；{b}\n星桥控股有限公司持有{a} 100% 股权、持有{b} 80% 股权，并控制两家公司的董事会。\n适用范围：上述主体，截至 2026-11-01。',
            '公司登记摘录 · 虚构样例'))
    if group in ('independent','conflict'):
        materials.append(material(cid+'-N','控制关系核对记录','registry',
            f'涉及主体：{a}；{b}\n{a}与{b}不存在共同控制。\n适用范围：2026-11-01 起的控制关系。',
            '登记变更材料 · 虚构样例'))
    return dict(id=cid,title=a.replace('有限公司','')+' × '+b.replace('有限公司',''),a=a,b=b,
        question='操作相似能否支持同一集团？是否需要区分代理关系？' if kind=='overlap' else '这两家公司是否属于同一集团？',
        context='核对候选关系，保留判断所依据的材料与范围。',owner='客户数据运营',
        region=['亚太','欧洲','拉美'][number%3],priority='候选关系核验',as_of='2026-11-06',
        status='调查中',materials=materials,library=[],revision=1,analysis=None,
        history=[],tasks=[],reviews=[],archived=False,sample=True,batch=BATCH_ID,
        signals={'shared_operation':kind=='overlap','same_app':kind=='overlap'},
        upstream={'suggestion':'same','label':'同一集团','reason':'操作重合' if kind=='overlap' else '主体关联线索','source':'模拟上游候选，不是标签'},
        graph_context={'left_members':[a]+[f'{a}关联主体{i}' for i in range(max(0,impact//2-1))],
                       'right_members':[b]+[f'{b}关联主体{i}' for i in range(max(0,impact-impact//2-1))]})

def batch_seeds():
    provider='远帆数字营销有限公司'
    return [
        make_case(1,'青禾科技有限公司',provider,agreement=True),
        make_case(2,'穗禾游戏有限公司',provider,agreement=True),
        make_case(3,'新镜科技有限公司',provider,agreement=True),
        make_case(4,'岚镜互动有限公司',provider,agreement=True,expired=True),
        make_case(5,'竹间网络有限公司',provider),
        make_case(6,'原野创意有限公司',provider,agreement=True,group='same'),
        make_case(7,'星河互动有限公司','星河数字有限公司',kind='registry',group='same',impact=11),
        make_case(8,'北岸科技有限公司','北岸传媒有限公司',kind='registry',group='conflict',impact=14),
        make_case(9,'暮山工作室有限公司','溪谷网络有限公司',kind='sparse'),
        make_case(10,'汀舟文化有限公司','汀舟传媒有限公司',kind='registry',group='independent'),
        make_case(11,'远林科技有限公司','远林数字有限公司',kind='registry',group='same'),
        make_case(12,'白榆互动有限公司','晨隙服务有限公司',kind='sparse',agreement=True,unverified=True),
    ]
