from copy import deepcopy

TODAY='2026-11-06'

def material(id,title,kind,text,source,date='2026-11-01',verified=True,expires=''):
    return dict(id=id,title=title,kind=kind,text=text,source=source,date=date,verified=verified,expires=expires,active=True)

AGENCY=material('LD-03','广告服务授权书 · Q4','agreement','''广告服务授权书（虚构样例）
涉及主体：蓝渡科技有限公司；远帆数字营销有限公司
蓝渡科技有限公司委托远帆数字营销有限公司，为 BlueTrail App 提供广告账户操作、素材上传及投放执行服务。
适用范围：BlueTrail App，2026 年第四季度。
授权有效期：2026-10-01 至 2026-12-31。
本授权不构成股权、控制关系或预算审批权的证明。
双方授权代表已签署，原件由客户资料负责人核对。''','客户资料负责人 · 已核对签署原件',expires='2026-12-31')
BUDGET=material('LD-04','BlueTrail Q4 预算审批确认','approval','''预算审批确认（虚构样例）
涉及主体：蓝渡科技有限公司；远帆数字营销有限公司
蓝渡科技有限公司与远帆数字营销有限公司用于 BlueTrail App 的投放账户，在本期活动内统一由蓝渡科技有限公司市场负责人最终审批预算。远帆数字营销有限公司负责执行，不具有本期预算最终审批权。
适用范围：BlueTrail App，2026 年第四季度；不适用于其他 App 或后续季度。
确认日期：2026-11-03。该记录由两方客户经理交叉核实。''','客户经理 · 双方书面确认',date='2026-11-03',expires='2026-12-31')
GROUP=material('CY-01','澄屿企业登记摘录','registry','''企业登记摘录（虚构样例）
涉及主体：澄屿互动有限公司；澄屿数字科技有限公司
截至登记日期，澄屿控股有限公司持有澄屿互动有限公司 100% 股权、持有澄屿数字科技有限公司 80% 股权，并控制两家公司的董事会。
适用范围：上述两家公司，截至 2026-11-01 的控制关系。
登记摘录由客户资料负责人核对。此记录不说明广告预算审批安排。''','企业登记资料 · 资料负责人核对')
CONFLICT=material('CY-03','最新控制关系变更摘录','registry','''企业登记变更摘录（虚构样例）
涉及主体：澄屿互动有限公司；澄屿数字科技有限公司
本材料记载澄屿数字科技有限公司已转让给独立投资人，与澄屿互动有限公司不存在共同控制。
适用范围：2026-11-01 起。待核对登记编号与生效条件；当前与另一份摘录冲突。''','企业登记变更 · 待核对版本',verified=True)

SEEDS=[
 dict(id='rel-blue',title='蓝渡 × 远帆',a='蓝渡科技有限公司',b='远帆数字营销有限公司',question='两家公司推同一个 App，可以按同一广告主看待吗？',context='销售在整理客户覆盖时发现操作与投放对象重合，希望判断客户是否重复覆盖。',owner='林可 · 客户经理',region='亚太',priority='客户覆盖核验',as_of=TODAY,status='调查中',materials=[
 material('LD-01','账户操作关联记录','signal','''账户操作关联记录（虚构样例）
涉及主体：蓝渡科技有限公司；远帆数字营销有限公司
最近 30 天，两家公司的广告账户有 18 天使用同一办公出口 IP；操作联系人有重合。
该记录仅反映共享操作环境，未包含股权、控制关系和预算审批信息。''','平台操作日志 · 虚构导出'),
 material('LD-02','推广对象关联记录','signal','''投放对象记录（虚构样例）
涉及主体：蓝渡科技有限公司；远帆数字营销有限公司
两家公司的广告账户均推广 BlueTrail App。App 商店登记的开发者为蓝渡科技有限公司。
投放行为不能区分集团协同与代理代投。''','广告对象清单 · 虚构导出')],library=[AGENCY,BUDGET]),
 dict(id='rel-island',title='澄屿互动 × 澄屿数字',a='澄屿互动有限公司',b='澄屿数字科技有限公司',question='两家公司能否加入同一个集团视图？',context='客户资料负责人已取得登记摘录，申请补全集团关系；无需变更广告账户或预算。',owner='周宁 · 客户资料',region='中国',priority='集团档案补全',as_of=TODAY,status='调查中',materials=[GROUP],library=[CONFLICT]),
 dict(id='rel-mist',title='雾原 × 山屿',a='雾原工作室有限公司',b='山屿网络有限公司',question='共享联系人是否说明这两家公司属于同一集团？',context='新客户信息有限，现有联系人相同，登记材料尚未取得。',owner='许晓 · 客户经理',region='东南亚',priority='新客户核验',as_of=TODAY,status='调查中',materials=[material('WY-01','联系人比对记录','signal','''联系人记录（虚构样例）
涉及主体：雾原工作室有限公司；山屿网络有限公司
两家公司填报了同一个业务联系人。尚未取得任一公司的有效登记摘录。
同一联系人可能来自共同服务机构，不能说明实际控制关系。''','客户表单 · 虚构导出')],library=[])
]

def seeds():
    out=deepcopy(SEEDS)
    for c in out:
        c.update(revision=1,analysis=None,history=[],tasks=[],reviews=[],archived=False,sample=True)
    return out
