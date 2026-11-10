from html import escape
CASES = {
 'agency': dict(title='澄海游戏 × 云帆营销', companies=['澄海游戏有限公司','云帆数字营销有限公司'], org='澄海游戏有限公司', agency='云帆数字营销有限公司', app='潮汐岛', until='2027-12-31', kind='agency'),
 'transfer': dict(title='星原科技 × 微澜互动', companies=['星原科技有限公司','微澜互动有限公司'], org='星原科技有限公司', agency='微澜互动有限公司', app='星际农场', until='2027-06-30', kind='agency'),
 'expired': dict(title='北川科技 × 远山传媒', companies=['北川科技有限公司','远山传媒有限公司'], org='北川科技有限公司', agency='远山传媒有限公司', app='山间集市', until='2025-06-30', kind='expired'),
 'conflict': dict(title='南屿互动 × 清禾传媒', companies=['南屿互动有限公司','清禾传媒有限公司'], org='南屿互动有限公司', agency='清禾传媒有限公司', app='岛屿笔记', until='2027-12-31', kind='conflict'),
}

def catalog(origin):
    return [dict(id=k,title=v['title'],companies=v['companies'],description={'agency':'共同投放信号，存在代理材料','transfer':'将已确认的方法用于新公司','expired':'历史授权是否仍然有效？','conflict':'代理材料与股权材料并存'}[v['kind']] if k!='transfer' else '将已确认的方法用于新公司',url=origin+'/sample-site/'+k+'/overview') for k,v in CASES.items()]

def page(case, document):
    c=CASES[case]; base='/sample-site/'+case
    docs={
      'overview': ('客户核验资料目录',f'<p>待核验主体：<strong>{c["org"]}</strong> 与 <strong>{c["agency"]}</strong>。</p><p>初筛信号：过去 30 天存在共同办公出口 IP，两个账户都推广 App「{c["app"]}」。初筛标签：疑似同集团。初筛信号并非已核实的公司关系。</p><p>请分别核验集团、代理、预算决策三个维度。材料索引见下方。</p>'),
      'partners': ('合作伙伴介绍', f'<p>{c["org"]} 与 {c["agency"]} 是长期商业合作伙伴，双方共同参与「{c["app"]}」的市场推广。</p><p>本页仅介绍商业合作，不披露股权、控制关系或预算审批权。</p>'),
      'authorization': ('广告代理授权书', f'<p>委托方：{c["org"]}</p><p>受托方：{c["agency"]}</p><p>委托方授权受托方为 App「{c["app"]}」提供广告账户操作、素材上传及投放执行服务。</p><p>授权期限：2025-01-01 至 {c["until"]}。</p><p>本授权不涉及股权转让、公司控制关系或最终预算审批权。</p><p>文件标识：AUTH-{case.upper()}-2025；发布方：{c["org"]}。</p>'),
      'registry': ('企业主体登记摘要', f'<p>主体一：{c["org"]}。主体二：{c["agency"]}。</p>'+ (f'<p>2026-09-01 生效：{c["org"]} 持有 {c["agency"]} 100% 股权并控制该公司。</p><p>代理授权与集团控制关系可以同时存在。预算审批权不在本摘要披露范围内。</p>' if c['kind']=='conflict' else '<p>此摘要仅确认两个法律主体独立登记。完整股东及最终控制人信息未披露，不能据此判断是否同集团。</p>')),
    }
    title,body=docs.get(document,docs['overview'])
    nav=''.join(f'<a href="{base}/{k}">{t}</a>' for k,(t,_) in docs.items())
    return f'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>{escape(title)} · 核验资料</title><style>body{{font:17px/1.8 Georgia,"Songti SC",serif;margin:0;background:#f7f5ef;color:#26392f}}header{{padding:20px 40px;background:#e5edde;font:13px sans-serif}}main{{max-width:780px;margin:40px auto;padding:0 32px}}h1{{font-size:30px}}nav{{display:grid;gap:10px;border-top:1px solid #cbd4c7;padding-top:25px;margin-top:35px}}a{{color:#276448}}.tag{{font:12px sans-serif;letter-spacing:2px;color:#69816e}}</style><header>LINKDESK SAMPLE LIBRARY · 虚构公司与合成材料，仅用于方法验证</header><main><div class="tag">{escape(c['title'])}</div><h1>{escape(title)}</h1>{body}<nav>{nav}</nav></main></html>'''
