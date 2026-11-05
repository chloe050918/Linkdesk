export function createOperationsUI(ctx) {
  const {api,esc,icon,btn,modal,close,toast,getState,render}=ctx;
  let data=null,budget=4,seed='review-01',selectedRule=null,previewData=null;
  const state=()=>getState();
  const policies=()=>data?.policies||[];
  const rule=()=>policies().find(p=>p.id===selectedRule)||policies()[0];
  const caseButton=(id,label='打开核验')=>`<button class="btn small" data-case="${esc(id)}">${label}${icon('arrow',13)}</button>`;
  const pill=(text,tone='')=>`<span class="ops-pill ${tone}">${esc(text)}</span>`;
  const label=v=>v?'可生成草稿':'保留单独处理';
  async function load(){data=await api(`operations?budget=${budget}&seed=${encodeURIComponent(seed)}`);return data;}
  async function refresh(){await load();render();}
  function summary(){const q=data.queue;return `<div class="ops-metrics"><div><strong>${q.total}</strong><span>本批候选关系</span></div><div><strong>${q.cluster.length}</strong><span>共享操作模式</span></div><div><strong>${q.prepared}</strong><span>逐案草稿已准备</span></div><div><strong>${q.archived}</strong><span>已复核入档</span></div></div>`;}
  function queuePage(){
    if(!data)return '<div class="empty">正在读取复核队列…</div>';
    const q=data.queue;
    return `<div class="ops-heading"><div><div class="eyebrow">REVIEW OPERATIONS / 01</div><h1>先决定，哪些判断值得专家时间。</h1><p class="sub mt">核对高影响关系，处理反复出现的问题，同时留一席抽检盲区。</p></div><div class="ops-batch">NOV · 2026<br><b>关系核验批次 01</b><span>合成案例 · 本地证据分析</span></div></div>${summary()}
    <section class="ops-feature"><div class="ops-feature-body"><span class="eyebrow">REPEATED PATTERN</span><h2>${q.cluster.length} 个案例，都因共享操作被关联</h2><p>共同信号相似，证据却不相同。${q.eligible} 个具备有效代理授权且无明确控制关系；其余需分别处理。</p><div class="ops-mini-flow"><span>核对代表案例</span>${icon('arrow',13)}<span>保存检查模板</span>${icon('arrow',13)}<span>验证后逐案复用</span></div>${btn('查看这一组 '+icon('arrow'),'ops-patterns','primary')}</div><div class="ops-pattern-visual" aria-label="六个候选关联共同连接远帆营销，不能由此推断同集团"><span class="pattern-center">远帆营销<br><small>共同操作方</small></span><div>${q.cluster.map(r=>`<span class="pattern-leaf ${r.eligible?'ready':''}">${esc(r.title.split(' × ')[0])}<i>${r.eligible?'授权有效':'独立核对'}</i></span>`).join('')}</div><p>相似模式 ≠ 相同结论</p></div></section>
    <section class="card ops-plan"><div class="card-head"><div><h2>本轮专家安排</h2><p class="sub mt">按材料冲突、关联影响、代表性排序；保留 1 个随机抽检位。</p></div><div class="row"><label class="ops-select">本轮名额<select id="ops-budget" aria-label="本轮复核名额">${[3,4,5,6].map(n=>`<option value="${n}" ${budget===n?'selected':''}>${n} 项</option>`).join('')}</select></label>${btn('更换抽检','ops-sample','small')}${btn('保存安排','ops-save-plan','small')}</div></div><div class="ops-plan-list">${q.selected.map((r,i)=>`<div class="ops-plan-row"><span class="ops-index">0${i+1}</span><div><div class="row"><b>${esc(r.title)}</b>${pill(r.selection,r.selection==='随机抽检'?'blue':r.rank===0?'red':'')}</div><p>${esc(r.reason)}</p></div>${caseButton(r.id)}</div>`).join('')||'<div class="empty">没有待安排的案例。</div>'}</div><div class="ops-note">抽检种子 ${esc(q.seed)} · 相同数据与种子可重现安排。${data.plans.length?'最近保存 '+esc(data.plans[0].id)+'，共 '+data.plans[0].selected.length+' 项。':'安排仅保存在工作区，不会自动通知同事。'}</div></section>
    <section class="card mt"><div class="card-head"><h2>全部候选关系</h2><span class="mode">原始建议保留；尚未核验不作为标签</span></div><div class="table-wrap"><table class="ops-table"><thead><tr><th>候选主体 / 地区</th><th>上游建议</th><th>处理路径</th><th>证据状态</th><th></th></tr></thead><tbody>${q.rows.map(r=>`<tr><td><b>${esc(r.title)}</b><small>${esc(r.region)} · ${esc(r.id)}</small></td><td>${esc(r.upstream.label)}<small>模拟模型输出</small></td><td>${pill(r.route,r.rank===0?'red':'')}<small>${esc(r.status)}</small></td><td>${r.prepared?pill('草稿已准备','green'):`${esc(r.group)}<small>代理：${esc(r.agency)}</small>`}</td><td>${caseButton(r.id,'查看')}</td></tr>`).join('')}</tbody></table></div></section>`;
  }
  function sources(){return state().cases.filter(c=>c.batch&&!c.hidden&&c.analysis?.dimensions.group.value==='unknown'&&c.reviews.some(r=>r.status==='approved'&&r.selected.includes('agency')));}
  function patternsPage(){
    if(!data)return '<div class="empty">正在读取…</div>';
    const q=data.queue,source=sources()[0];
    return `<div class="ops-heading"><div><div class="eyebrow">PATTERN INVESTIGATION / 02</div><h1>共享操作，是否来自代理投放？</h1><p class="sub mt">先复核一个有依据的案例，再检查同类案例是否满足同样条件。</p></div>${btn('返回本轮安排','ops-queue','small')}</div><div class="ops-two mt"><section class="card"><div class="card-head"><h2>共同线索</h2>${pill(q.cluster.length+' 项')}</div><div class="card-body"><div class="ops-signal">${icon('link')}共享办公出口 IP</div><div class="ops-signal">${icon('grid')}推广同一 App</div><p class="sub mt">分组来自两个结构化信号。它只缩小核验范围，不证明同集团，也不允许批量确认关系。</p></div></section><section class="card"><div class="card-head"><h2>${source?'代表案例已复核':'先核对代表案例'}</h2>${pill(source?'可以沉淀模板':'待人工确认',source?'green':'')}</div><div class="card-body"><h3>${esc(source?.title||state().cases.find(c=>c.id==='batch-01')?.title||'代表案例')}</h3><p class="sub mt">有本案授权原文。确认代理关系，并将集团关系保留为未知。</p><div class="row mt">${caseButton(source?.id||'batch-01','核对案例')}${source?btn('沉淀检查模板','ops-create','primary',`data-source="${esc(source.id)}"`):''}</div></div></section></div>
    <section class="card mt"><div class="card-head"><h2>同类案例，逐一核对适用性</h2><span class="mode">每案使用自己的材料</span></div><div class="table-wrap"><table class="ops-table"><thead><tr><th>候选主体</th><th>代理证据</th><th>控制关系</th><th>模板适用性</th><th></th></tr></thead><tbody>${q.cluster.map(r=>`<tr><td><b>${esc(r.title)}</b><small>${esc(r.status)}</small></td><td>${esc(r.agency)}</td><td>${esc(r.group)}</td><td>${pill(r.eligible?'满足证据条件':'需单独核验',r.eligible?'green':'amber')}${r.prepared?'<small>已有复核草稿</small>':''}</td><td>${caseButton(r.id,'看依据')}</td></tr>`).join('')}</tbody></table></div></section>
    <div class="ops-callout"><b>复用的是检查方法，不是公司的关系标签。</b><p>过期授权、无授权、同时具有同集团证明的案例，都不能继承代表案例的判断。规则启用后，只生成带本案引用的待确认草稿。</p></div>${policies().length?btn('查看检查模板与回归结果 '+icon('arrow'),'ops-rules','primary mt'):''}`;
  }
  function rulesPage(){
    const p=rule();
    if(!p)return `<div class="ops-heading"><div><div class="eyebrow">REUSABLE CHECKS / 03</div><h1>把一次核验，沉淀成可检查的方法。</h1><p class="sub mt">检查模板必须来自已复核案例，验证边界后才能生成新的草稿。</p></div></div><section class="card mt"><div class="empty"><h2>还没有检查模板</h2><p class="mt mb">先完成“青禾 × 远帆”的代理关系复核，再沉淀模板。</p>${btn('进入同类问题','ops-patterns','primary')}</div></section>`;
    const e=p.evaluation;
    return `<div class="ops-heading"><div><div class="eyebrow">REUSABLE CHECKS / 03</div><h1>检查模板与边界验证</h1><p class="sub mt">每一次复用都要保留来源、版本和逐案证据。</p></div>${pill(p.effective_label,p.effective?'green':p.source_valid?'':'red')}</div>
    <div class="ops-rule-tabs">${policies().map(x=>btn(esc(x.id),'ops-select-rule',x.id===p.id?'primary small':'small',`data-rule="${esc(x.id)}"`)).join('')}</div>
    <section class="card"><div class="card-head"><h2>${esc(p.name)}</h2><span class="mode">${esc(p.version)}</span></div><div class="card-body"><p>${esc(p.rationale)}</p><div class="ops-rule-grid mt"><div><b>适用前提</b><p>同 IP + 同 App；本案有有效且已核对的代理授权；控制关系尚未确认。</p></div><div><b>必须排除</b><p>授权失效、来源未核对、控制关系冲突，或已有控制关系证明。</p></div><div><b>生成的结果</b><p>代理关系复核草稿 + 本案引用。集团关系保留未知，仍需人工提交与复核。</p></div></div><div class="row spread mt"><div class="mode">来源 ${esc(p.source_title)} / ${esc(p.source_review_id)}${!p.source_valid?' · 来源已失效，请建立新版本':''}</div>${caseButton(p.source_id,'看来源')}</div></div></section>
    <section class="card mt"><div class="card-head"><div><h2>先验证边界，再启用</h2><p class="sub mt">固定合成样本检查“能否套用模板”，不衡量线上关系识别准确率。</p></div>${btn(e?'重新运行回归':'运行边界验证','ops-evaluate','primary',p.source_valid?'':'disabled')}</div>${e?`<div class="ops-eval-score"><div><strong>${e.passed}<small> / ${e.total}</small></strong><span>边界检查通过</span></div><div><strong>${e.baseline_passed}<small> / ${e.total}</small></strong><span>简化对照：只按操作相似套用</span></div><p>对照是故意省略证据条件的规则，<br>不是现有业务系统的效果。</p></div><div class="table-wrap"><table class="ops-table"><thead><tr><th>边界场景</th><th>预期</th><th>实际</th><th>检查</th></tr></thead><tbody>${e.rows.map(r=>`<tr><td>${esc(r.name)}<small>${esc(r.id)}</small></td><td>${label(r.expected)}</td><td>${label(r.actual)}</td><td>${pill(r.passed?'通过':'失败',r.passed?'green':'red')}</td></tr>`).join('')}</tbody></table></div><div class="ops-note">${esc(e.suite_version)} · 数据摘要 ${esc(e.dataset_sha256.slice(0,12))} · ${esc(e.notice)}</div>`:'<div class="empty">尚未验证。检查包括有效授权、过期、缺失、主体不匹配、否定陈述、同集团反例和材料冲突。</div>'}</section>
    <div class="ops-rule-actions"><div><b>${p.effective?'模板已启用，可预览适用范围':'模板状态：'+esc(p.effective_label)}</b><p class="sub mt">启用不会改写标签；生成草稿前会再次检查每个案例。</p></div><div class="row">${p.effective?btn('停用','ops-disable',''):btn('启用模板','ops-activate','',(!e||e.failed||!p.source_valid)?'disabled':'')}${btn('预览可复用案例 '+icon('arrow'),'ops-preview','primary',p.effective?'':'disabled')}<a class="btn" href="/api/policies/${esc(p.id)}/export" download>导出规则与回归</a></div></div><details class="ops-history"><summary>规则操作记录</summary>${p.history.map(h=>`<p>${esc(h.at)} · ${esc(h.text)}</p>`).join('')}</details>`;
  }
  function createModal(source){
    modal('从复核结果沉淀检查模板',`<div class="info-box mb">来源：${esc(source.title)}。保存的是检查条件和证据要求，不会传播公司的关系标签。</div><label class="field">可复用的业务判断<textarea id="ops-rationale">共享操作和同 App 可能来自代理代投。每案先核对有效授权，存在控制关系证据或冲突时单独处理；只准备代理关系复核，不据此认定同集团或无集团关系。</textarea></label><p class="sub">模板条件固定为保守版本。保存后需运行边界验证，再决定是否启用。</p>`,`${btn('取消','close')}${btn('保存模板草稿','ops-save-rule','primary',`data-source="${esc(source.id)}"`)}`,true);
  }
  async function handle(action,el){
    if(action==='ops-queue'||action==='ops-patterns'||action==='ops-rules'){state().page=action.slice(4);await refresh();return;}
    if(action==='ops-sample'){seed='review-'+Date.now();await refresh();return;}
    if(action==='ops-save-plan'){let p=await api('review-plans',{budget,seed});await refresh();toast('已保存 '+p.selected.length+' 项复核安排');return;}
    if(action==='ops-create'||action==='ops-create-from-case'){
      let id=el.dataset.source||state().id,source=state().cases.find(c=>c.id===id);
      if(!source)return;createModal(source);return;
    }
    if(action==='ops-save-rule'){
      let p=await api('policies',{source_id:el.dataset.source,rationale:document.querySelector('#ops-rationale').value});selectedRule=p.id;close();state().page='rules';await refresh();return;
    }
    if(action==='ops-select-rule'){selectedRule=el.dataset.rule;render();return;}
    const p=rule();if(!p)return;
    if(['ops-evaluate','ops-activate','ops-disable'].includes(action)){
      await api(`policies/${p.id}/${action.slice(4)}`,{});await refresh();toast(action==='ops-evaluate'?'边界验证已完成':action==='ops-activate'?'模板已启用，未修改任何标签':'模板已停用');return;
    }
    if(action==='ops-preview'){
      previewData=await api(`policies/${p.id}/preview`,{});
      modal('逐案检查，再生成复核草稿',`<p class="sub mb">只使用每个案例自己的授权材料。不可套用的案例保留原因，不会批量确认集团或代理标签。</p>${previewData.rows.map(r=>`<label class="check ops-preview-row"><input type="checkbox" name="ops-apply" value="${esc(r.id)}" ${r.eligible?'checked':'disabled'}><span><strong>${esc(r.title)} ${pill(r.eligible?'可生成草稿':'不套用',r.eligible?'green':'')}</strong><small>${esc(r.reason)}</small>${r.eligible?`<small>本案引用：${r.refs.map(esc).join('、')}</small>`:''}</span></label>`).join('')}<div class="info-box">未勾选项保持原状。生成的草稿仍需人工提交与业务复核。</div>`,`${btn('取消','close')}${btn('生成所选复核草稿','ops-apply','primary',previewData.rows.some(r=>r.eligible)?'':'disabled')}`,true);return;
    }
    if(action==='ops-apply'){
      const ids=[...document.querySelectorAll('[name="ops-apply"]:checked')].map(e=>e.value);
      const result=await api(`policies/${p.id}/apply`,{ids,token:previewData.token});
      for(const c of result.cases){const i=state().cases.findIndex(x=>x.id===c.id);state().cases[i]=c;}
      close();state().page='patterns';await refresh();toast(`已生成 ${result.count} 份草稿，等待逐案确认`);return;
    }
  }
  function detailBanner(c){if(!c.batch)return '';
    const draft=c.prepared&&!c.archived&&c.status!=='待复核'&&c.analysis?.fingerprint===c.prepared.fingerprint&&!ctx.isStale(c);
    return `<div class="ops-detail-nav">${btn('← 本轮复核','ops-queue','ghost small')}<span>上游候选：${esc(c.upstream?.label)} · 未核验</span>${btn('查看同类问题','ops-patterns','ghost small')}</div>${draft?`<div class="ops-draft-banner"><div><b>本案复核草稿已准备</b><p>来自 ${esc(c.prepared.policy_id)}，引用 ${c.prepared.refs.map(esc).join('、')}。只准备代理复核，集团关系保持未知。</p></div>${btn('查看并提交草稿','submit','primary small')}</div>`:''}`;
  }
  document.addEventListener('change',async e=>{if(e.target.id==='ops-budget'){budget=Number(e.target.value);try{await refresh()}catch(err){toast(err.message)}}});
  return {load,refresh,handle,detailBanner,page:p=>p==='queue'?queuePage():p==='patterns'?patternsPage():rulesPage()};
}
