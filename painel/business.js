/* Fluxos comerciais; carregado antes de a inicialização assíncrona renderizar. */
const reais = cents => (Number(cents||0)/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const dia = value => value ? value.split('-').reverse().join('/') : 'Sem previsão';
const OP_ESTADO={aberta:'Aberta',ganha:'Ganha',perdida:'Perdida'};
const campo=(name,label,value='',type='text',extra='')=>`<label class="field">${label}<input class="in" name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const dadosForm=form=>Object.fromEntries(new FormData(form));
async function salvarComercial(lid,path,method,body){
  const novo=await api(`/api/leads/${encodeURIComponent(lid)}/${path}`,{method,body});
  upsertLead(novo);
  if(leadAberto?.id===lid){leadAberto=novo;desenhaLead();}
  atualizarAvisos();return novo;
}
function comercialCampos(l){
  return `<div class="row section-gap"><button class="btn sm" id="editarContato">Editar contato</button></div><div id="contactEditor"></div>
  <details class="crm-section"><summary>Tags e prioridade ${tagsLead(l)}</summary><form id="orgForm" class="crm-form"><div class="form-grid">${campo('tags','Tags (separadas por vírgula)',(l.tags||[]).join(', '),'text','maxlength="819"')}<label class="field">Prioridade<select class="in" name="prioridade">${Object.entries(PRIORIDADES).map(([v,n])=>`<option value="${v}" ${(l.prioridade||'normal')===v?'selected':''}>${n}</option>`).join('')}</select></label></div><button class="btn sm pri">Salvar organização</button></form></details>
  <details class="crm-section" open><summary>Oportunidades <span>${(l.oportunidades||[]).length}</span></summary>
    ${(l.oportunidades||[]).map(o=>`<div class="crm-item"><div><b>${esc(o.servico)}</b><small>${reais(o.valor_centavos)} · ${esc(OP_ESTADO[o.estado])} · ${dia(o.previsao)}</small></div><div class="row"><button class="btn sm" data-op-edit="${o.id}">Editar</button><button class="btn sm danger" data-item-delete="oportunidades/${o.id}" aria-label="Excluir oportunidade ${esc(o.servico)}">${ic('trash')}</button></div></div>`).join('')}
    <form id="opForm" class="crm-form"><input type="hidden" name="id"><div class="form-grid">${campo('servico','Serviço oferecido','','text','required maxlength="200"')}${campo('valor','Valor (R$)','','number','required min="0" max="999999999.99" step="0.01"')}${campo('previsao','Previsão de fechamento','','date')}<label class="field">Situação<select class="in" name="estado">${Object.entries(OP_ESTADO).map(([v,n])=>`<option value="${v}">${n}</option>`).join('')}</select></label></div><div class="row"><button class="btn pri sm" type="submit">Salvar oportunidade</button><button class="btn sm" type="reset">Nova / limpar</button></div></form>
  </details>
  <details class="crm-section" open><summary>Tarefas <span>${(l.tarefas||[]).filter(t=>!t.concluida).length} pendentes</span></summary>
    ${(l.tarefas||[]).slice().sort((a,b)=>a.concluida-b.concluida||a.prazo-b.prazo).map(t=>`<div class="crm-item ${!t.concluida&&t.prazo<Date.now()/1000?'overdue':''}"><div><b>${esc(t.titulo)}</b><small>${t.concluida?'Concluída':t.prazo<Date.now()/1000?'Atrasada':'Pendente'} · ${fData(t.prazo)}</small></div><div class="row"><button class="btn sm" data-task-toggle="${t.id}">${t.concluida?'Reabrir':'Concluir'}</button><button class="btn sm" data-task-edit="${t.id}" aria-label="Editar tarefa ${esc(t.titulo)}">Editar</button><button class="btn sm danger" data-item-delete="tarefas/${t.id}" aria-label="Excluir tarefa ${esc(t.titulo)}">${ic('trash')}</button></div></div>`).join('')}
    <form id="taskForm" class="crm-form"><input type="hidden" name="id"><div class="form-grid">${campo('titulo','Tarefa','','text','required maxlength="200"')}${campo('prazo','Prazo','','datetime-local','required')}</div><div class="row"><button class="btn pri sm" type="submit">Salvar tarefa</button><button class="btn sm" type="reset">Nova / limpar</button></div></form>
  </details>`;
}
function conectaComercial(l){
  $('#orgForm').onsubmit=async e=>{e.preventDefault();const d=dadosForm(e.currentTarget);d.tags=d.tags.split(',').map(t=>t.trim()).filter(Boolean);await salvarComercial(l.id,'organizacao','PATCH',d);toast('Organização salva');};
  $('#editarContato').onclick=()=>{
    $('#contactEditor').innerHTML=`<form id="contactForm" class="crm-form">${contatoInputs(l)}<button class="btn pri sm">Salvar contato</button></form>`;
    $('#contactForm').onsubmit=async e=>{e.preventDefault();await salvarComercial(l.id,'contatos','PATCH',dadosForm(e.currentTarget));toast('Contato atualizado');};
  };
  $('#opForm').onsubmit=async e=>{
    e.preventDefault();const d=dadosForm(e.currentTarget),id=d.id;delete d.id;
    await salvarComercial(l.id,'oportunidades'+(id?'/'+id:''),id?'PATCH':'POST',d);toast('Oportunidade salva');
  };
  $$('[data-op-edit]').forEach(b=>b.onclick=()=>{const o=l.oportunidades.find(x=>x.id===b.dataset.opEdit),f=$('#opForm');for(const k of ['id','servico','previsao','estado'])f.elements[k].value=o[k]||'';f.elements.valor.value=o.valor_centavos/100;f.elements.servico.focus();});
  $('#taskForm').onsubmit=async e=>{
    e.preventDefault();const d=dadosForm(e.currentTarget),id=d.id;delete d.id;d.prazo=new Date(d.prazo).getTime()/1000;
    await salvarComercial(l.id,'tarefas'+(id?'/'+id:''),id?'PATCH':'POST',d);toast('Tarefa salva');
  };
  $$('[data-task-edit]').forEach(b=>b.onclick=()=>{const t=l.tarefas.find(x=>x.id===b.dataset.taskEdit),f=$('#taskForm');f.elements.id.value=t.id;f.elements.titulo.value=t.titulo;f.elements.prazo.value=localDate(t.prazo);f.elements.titulo.focus();});
  $$('[data-task-toggle]').forEach(b=>b.onclick=async()=>{const t=l.tarefas.find(x=>x.id===b.dataset.taskToggle);await salvarComercial(l.id,'tarefas/'+t.id,'PATCH',{concluida:!t.concluida});toast(t.concluida?'Tarefa reaberta':'Tarefa concluída');});
  $$('[data-item-delete]').forEach(b=>b.onclick=async()=>{if(await confirmar('Remover registro','Remover este registro da ficha?','Remover'))await salvarComercial(l.id,b.dataset.itemDelete,'DELETE');});
}
function todasTarefas(){
  return S.leads.flatMap(l=>[
    ...(l.tarefas||[]).map(t=>({...t,lead:l})),
    ...(l.retorno&&!['fechado','descartado'].includes(l.status)?[{id:'retorno',titulo:'Retorno agendado',prazo:l.retorno,concluida:false,lead:l}]:[])
  ]).sort((a,b)=>a.prazo-b.prazo);
}
function atualizarAvisos(){
  let alert=$('#taskAlert');
  if(!alert){alert=document.createElement('a');alert.id='taskAlert';alert.className='task-alert';alert.href='#/agenda';$('.topbar').insertBefore(alert,$('.topbar .sp'));}
  const count=todasTarefas().filter(t=>!t.concluida&&t.prazo<Date.now()/1000).length;
  alert.hidden=!count;alert.textContent=`${count} tarefa${count===1?'':'s'} atrasada${count===1?'':'s'}`;
}
setInterval(()=>{if(!document.hidden)atualizarAvisos();},30000);
const renderAnterior=render;
render=function(){sincronizaEtapas();renderAnterior();atualizarAvisos();};
VIEWS.oportunidades=()=>{
  crumbs([['Oportunidades']]);
  const rows=S.leads.flatMap(l=>(l.oportunidades||[]).map(o=>({...o,lead:l})));
  const sum=state=>rows.filter(o=>o.estado===state).reduce((s,o)=>s+o.valor_centavos,0);
  $('#page').innerHTML=`<div class="ph"><div><h1>Oportunidades</h1><p>Negociações por serviço. Abra um lead para cadastrar ou editar.</p></div><a class="btn pri" href="#/leads">Escolher lead</a></div><div class="grid g3">${[['Em aberto',sum('aberta')],['Vendas ganhas',sum('ganha')],['Vendas perdidas',sum('perdida')]].map(([n,v])=>`<div class="card kpi"><div class="l">${n}</div><div class="n money">${reais(v)}</div></div>`).join('')}</div><div class="card section-gap"><div class="tbar"><label>Situação <select class="in" id="opFiltro"><option value="">Todas</option>${Object.entries(OP_ESTADO).map(([v,n])=>`<option value="${v}">${n}</option>`).join('')}</select></label></div><div id="opRows"></div></div>`;
  const draw=()=>{$('#opRows').innerHTML=tabelaComercial(['Lead','Serviço','Valor','Previsão','Situação'],rows.filter(o=>!$('#opFiltro').value||o.estado===$('#opFiltro').value).map(o=>[`<a href="#" data-lead="${o.lead.id}">${esc(o.lead.nome)}</a>`,esc(o.servico),reais(o.valor_centavos),dia(o.previsao),OP_ESTADO[o.estado]]));};
  $('#opFiltro').onchange=draw;draw();
};
function tabelaComercial(headers,rows){return rows.length?`<div class="twrap"><table class="t"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<div class="empty">Nenhum registro encontrado.</div>';}
VIEWS.agenda=()=>{
  crumbs([['Tarefas e retornos']]);
  $('#page').innerHTML=`<div class="ph"><div><h1>Tarefas e retornos</h1><p>Os avisos de atraso aparecem enquanto o painel está aberto.</p></div><a class="btn" href="#/leads">Agendar na ficha do lead</a></div><div class="card"><div class="tbar"><label>Exibir <select class="in" id="taskFilter"><option value="pendentes">Pendentes</option><option value="atrasadas">Atrasadas</option><option value="hoje">Hoje</option><option value="concluidas">Concluídas</option><option value="todas">Todas</option></select></label></div><div id="taskRows"></div></div>`;
  const draw=()=>{
    const f=$('#taskFilter').value,now=Date.now()/1000;
    const rows=todasTarefas().filter(t=>f==='todas'||(f==='concluidas'?t.concluida:!t.concluida&&(f==='pendentes'||(f==='atrasadas'?t.prazo<now:new Date(t.prazo*1000).toDateString()===new Date().toDateString()))));
    $('#taskRows').innerHTML=tabelaComercial(['Tarefa','Lead','Prazo','Situação','Ação'],rows.map(t=>[esc(t.titulo),`<a href="#" data-lead="${t.lead.id}">${esc(t.lead.nome)}</a>`,fData(t.prazo),t.concluida?'Concluída':t.prazo<now?'<span class="overdue">Atrasada</span>':'Pendente',`<button class="btn sm" data-finish="${t.id}" data-lid="${t.lead.id}">${t.concluida?'Reabrir':'Concluir'}</button>`]));
    $$('[data-finish]').forEach(b=>b.onclick=async()=>{const t=rows.find(x=>x.id===b.dataset.finish&&x.lead.id===b.dataset.lid);if(t.id==='retorno')upsertLead(await api('/api/leads/'+t.lead.id,{method:'PATCH',body:{retorno:null}}));else await salvarComercial(t.lead.id,'tarefas/'+t.id,'PATCH',{concluida:!t.concluida});atualizarAvisos();draw();});
  };$('#taskFilter').onchange=draw;draw();
};
function sincronizaEtapas(){
  if(!S.config?.etapas)return;
  STATUS.splice(0,STATUS.length,...S.config.etapas.map(s=>[s.id,s.nome]));
  for(const key of Object.keys(NOME_ST))delete NOME_ST[key];
  for(const s of S.config.etapas){NOME_ST[s.id]=s.nome;COR_ST[s.id]=s.cor;}
}

const CONTATO_LABELS={nome:'Nome da empresa',categoria:'Categoria',telefone:'Telefone',whatsapp:'WhatsApp',email:'E-mail',site:'Site',cidade:'Cidade',uf:'UF',bairro:'Bairro',endereco:'Endereço',cep:'CEP',instagram:'Instagram',facebook:'Facebook',linkedin:'LinkedIn'};
function contatoInputs(l={}){return `<div class="form-grid">${Object.entries(CONTATO_LABELS).map(([k,n])=>campo(k,n,l[k]||'','text',`maxlength="500" ${k==='nome'?'required':''}`)).join('')}</div>`;}
VIEWS.cadastro=()=>{
  crumbs([['Leads','#/leads'],['Cadastro manual']]);
  $('#page').innerHTML=`<div class="ph"><div><h1>Novo lead</h1><p>Cadastre empresas de indicações e outros canais.</p></div></div><form class="card business-form" id="manualForm">${contatoInputs()}<div class="row"><button class="btn pri">Cadastrar lead</button><a class="btn" href="#/leads">Cancelar</a></div></form>`;
  $('#manualForm').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{const l=await api('/api/leads/manual',{method:'POST',body:dadosForm(e.currentTarget)});upsertLead(l);location.hash='#/leads';await abreLead(l.id);toast('Lead cadastrado');}finally{button.disabled=false;}};
};
VIEWS.importar=()=>{
  crumbs([['Leads','#/leads'],['Importar CSV']]);
  $('#page').innerHTML=`<div class="ph"><div><h1>Importar leads</h1><p>CSV em UTF-8, até 5 MB e 5.000 linhas. Revise as colunas antes de confirmar.</p></div></div><div class="card business-form"><div class="form-grid"><label class="field">Arquivo CSV<input class="in" type="file" id="csvFile" accept=".csv,text/csv"></label><label class="field">Separador<select class="in" id="csvSep"><option value=";">Ponto e vírgula (;)</option><option value=",">Vírgula (,)</option><option value="tab">Tabulação</option></select></label></div><div id="csvMapping"></div><button class="btn" id="csvPreview">Pré-visualizar</button><div id="csvResult" class="section-gap"></div></div>`;
  let source='',mapping=null;
  const preview=async()=>{
    if(!source){toast('Escolha um arquivo CSV.');return;}
    const payload={csv:source,separador:$('#csvSep').value==='tab'?'\t':$('#csvSep').value,mapeamento:mapping};
    const r=await api('/api/leads/importar',{method:'POST',body:payload});
    $('#csvMapping').innerHTML=`<p class="hint">Associe as colunas. Nome é obrigatório; os demais campos podem ser ignorados.</p><div class="form-grid">${Object.entries(CONTATO_LABELS).map(([k,n])=>`<label class="field">${n}<select class="in" data-column="${k}"><option value="">Ignorar</option>${r.colunas.map(c=>`<option value="${esc(c)}" ${r.mapeamento[k]===c?'selected':''}>${esc(c)}</option>`).join('')}</select></label>`).join('')}</div>`;
    $$('[data-column]').forEach(sel=>sel.onchange=()=>{mapping=Object.fromEntries($$('[data-column]').filter(x=>x.value).map(x=>[x.dataset.column,x.value]));$('#csvResult').innerHTML='<p class="hint">Mapeamento alterado. Clique em Pré-visualizar novamente.</p>';});
    $('#csvResult').innerHTML=`<p>${r.validos} válidos · ${r.duplicados} duplicados · ${r.erros} com erro</p>${r.precisa_mapear?'<p class="overdue">Associe a coluna Nome e pré-visualize novamente.</p>':''}${tabelaComercial(['Linha','Nome','Resultado'],r.linhas.slice(0,100).map(x=>[x.linha,esc(x.nome),esc(x.estado+' '+x.mensagem)]))}${r.linhas.length>100?'<p class="hint">Exibindo as primeiras 100 linhas. Os totais incluem o arquivo inteiro.</p>':''}<button class="btn pri section-gap" id="csvConfirm" ${r.validos?'':'disabled'}>Importar ${r.validos} leads válidos</button>`;
    $('#csvConfirm').onclick=async()=>{if(!await confirmar('Importar leads',`Importar ${r.validos} leads? Duplicados e linhas com erro serão ignorados. Um backup será criado.`,'Importar'))return;$('#csvConfirm').disabled=true;try{const done=await api('/api/leads/importar',{method:'POST',body:{...payload,confirmar:true}});await carregaLeads();toast(`${done.importados} leads importados`);location.hash='#/leads';}catch(err){mostraErro(err.message);$('#csvConfirm').disabled=false;}};
  };
  $('#csvFile').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>5_000_000){mostraErro('O limite é 5 MB.');return;}source=await file.text();mapping=null;await preview();};
  $('#csvSep').onchange=()=>{mapping=null;$('#csvResult').innerHTML='';$('#csvMapping').innerHTML='';};
  $('#csvPreview').onclick=preview;
};
const leadsOriginal=VIEWS.leads;
VIEWS.leads=()=>{leadsOriginal();const acts=$('#page .acts');if(acts)acts.insertAdjacentHTML('afterbegin','<a class="btn pri" href="#/cadastro">Novo lead</a><a class="btn" href="#/importar">Importar CSV</a>');};

const PRIORIDADES={baixa:'Baixa',normal:'Normal',alta:'Alta',urgente:'Urgente'};
function tagsLead(l){return `<div class="tags">${l.prioridade&&l.prioridade!=='normal'?`<span>${PRIORIDADES[l.prioridade]||'Normal'}</span>`:''}${(l.tags||[]).map(t=>`<span>${esc(t)}</span>`).join('')}</div>`;}
function filtrosComerciais(){
  const tags=[...new Set(S.leads.flatMap(l=>l.tags||[]))].sort();
  return `<select class="in" id="ftag" aria-label="Filtrar por tag"><option value="">Todas as tags</option>${tags.map(t=>`<option value="${esc(t)}" ${FL.tag===t?'selected':''}>${esc(t)}</option>`).join('')}</select>
  <select class="in" id="fpriority" aria-label="Filtrar por prioridade"><option value="">Todas as prioridades</option>${Object.entries(PRIORIDADES).map(([v,n])=>`<option value="${v}" ${FL.prioridade===v?'selected':''}>${n}</option>`).join('')}</select>
  <select class="in" id="fsource" aria-label="Filtrar por busca"><option value="">Todas as buscas</option>${S.buscas.map(b=>`<option value="${b.id}" ${FL.busca===b.id?'selected':''}>${esc(b.parametros.nichos.join(', '))} · ${esc(b.parametros.cidade)}</option>`).join('')}</select>
  <select class="in" id="fsaved" aria-label="Filtros salvos"><option value="">Filtros salvos</option>${(S.config?.filtros||[]).map(f=>`<option value="${f.id}">${esc(f.nome)}</option>`).join('')}</select><button class="btn sm" id="fsave">Salvar filtros</button><button class="btn sm" id="fclear">Limpar filtros</button><button class="btn sm danger" id="fdelete" disabled>Excluir filtro salvo</button>`;
}
function conectaFiltros(el,salva){
  for(const [id,key] of [['ftag','tag'],['fpriority','prioridade'],['fsource','busca']])$('#'+id,el).onchange=e=>{FL[key]=e.target.value;salva();};
  $('#fclear',el).onclick=()=>{Object.keys(FL).forEach(k=>delete FL[k]);FL.texto='';salva();};
  $('#fsaved',el).onchange=e=>{const id=e.target.value,f=S.config.filtros.find(f=>f.id===id);if(!f)return;Object.keys(FL).forEach(k=>delete FL[k]);Object.assign(FL,{texto:''},f.filtros);salva();$('#fsaved',el).value=id;$('#fdelete',el).disabled=false;};
  $('#fsave',el).onclick=()=>{
    const wrap=document.createElement('form');wrap.className='row';wrap.style.flexWrap='wrap';wrap.innerHTML='<input class="in" name="nome" aria-label="Nome do filtro" placeholder="Nome do filtro" required maxlength="80"><button class="btn pri sm">Salvar</button><button class="btn sm" type="button">Cancelar</button>';
    $('#fsave',el).replaceWith(wrap);wrap.querySelector('[type=button]').onclick=salva;
    wrap.onsubmit=async e=>{e.preventDefault();S.config.filtros=await api('/api/filtros',{method:'POST',body:{nome:wrap.elements.nome.value,filtros:{...FL}}});salva();toast('Filtro salvo');};wrap.elements.nome.focus();
  };
  $('#fdelete',el).onclick=async()=>{const id=$('#fsaved',el).value;if(!id)return;if(!await confirmar('Excluir filtro','Excluir apenas esta combinação de filtros?','Excluir'))return;S.config.filtros=await api('/api/filtros/'+id,{method:'DELETE'});salva();};
}
VIEWS.etapas=()=>{
  crumbs([['Funil','#/funil'],['Configurar etapas']]);
  let stages=(S.config.etapas||[]).map(s=>({...s}));
  const original=stages.map(s=>({...s})),fixed=['novo','contatado','fechado','descartado'];
  $('#page').innerHTML=`<div class="ph"><div><h1>Etapas do funil</h1><p>Renomeie, ordene e crie etapas. Entrada, contato, ganho e descarte mantêm suas funções.</p></div></div><form class="card business-form" id="stageForm"><div id="stageRows"></div><div id="stageMigration"></div><div class="row"><button class="btn" type="button" id="stageAdd">Adicionar etapa</button><button class="btn pri" type="submit">Salvar funil</button></div></form>`;
  const draw=()=>{
    $('#stageRows').innerHTML=stages.map((s,i)=>`<div class="stage-row"><label class="field">${fixed.includes(s.id)?({novo:'Entrada',contatado:'Contato registrado',fechado:'Ganho',descartado:'Descarte'}[s.id]):'Etapa personalizada'}<input class="in" data-stage-name="${s.id}" value="${esc(s.nome)}" required maxlength="60"></label><input class="in" type="color" data-stage-color="${s.id}" value="${s.cor}" aria-label="Cor de ${esc(s.nome)}"><div class="row"><button class="btn sm" type="button" data-stage-up="${i}" ${i===0?'disabled':''} aria-label="Mover ${esc(s.nome)} para cima">↑</button><button class="btn sm" type="button" data-stage-down="${i}" ${i===stages.length-1?'disabled':''} aria-label="Mover ${esc(s.nome)} para baixo">↓</button><button class="btn sm danger" type="button" data-stage-remove="${s.id}" ${fixed.includes(s.id)?'disabled':''}>Remover</button></div></div>`).join('');
    $('#stageMigration').innerHTML=original.filter(s=>!stages.some(x=>x.id===s.id)&&S.leads.some(l=>l.status===s.id)).map(s=>`<label class="field section-gap">Mover leads de “${esc(s.nome)}” para<select class="in" required data-migrate="${s.id}"><option value="">Escolha uma etapa</option>${stages.map(x=>`<option value="${x.id}">${esc(x.nome)}</option>`).join('')}</select></label>`).join('');
    $$('[data-stage-name]').forEach(x=>x.oninput=()=>stages.find(s=>s.id===x.dataset.stageName).nome=x.value);
    $$('[data-stage-color]').forEach(x=>x.oninput=()=>stages.find(s=>s.id===x.dataset.stageColor).cor=x.value);
    $$('[data-stage-up]').forEach(b=>b.onclick=()=>{const i=+b.dataset.stageUp;[stages[i-1],stages[i]]=[stages[i],stages[i-1]];draw();});
    $$('[data-stage-down]').forEach(b=>b.onclick=()=>{const i=+b.dataset.stageDown;[stages[i+1],stages[i]]=[stages[i],stages[i+1]];draw();});
    $$('[data-stage-remove]').forEach(b=>b.onclick=()=>{stages=stages.filter(s=>s.id!==b.dataset.stageRemove);draw();});
  };
  $('#stageAdd').onclick=()=>{if(stages.length>=20)return toast('Limite de 20 etapas.');stages.splice(Math.max(0,stages.findIndex(s=>s.id==='fechado')),0,{id:'e'+crypto.randomUUID().replaceAll('-',''),nome:'Nova etapa',cor:'#006bf5'});draw();};
  $('#stageForm').onsubmit=async e=>{e.preventDefault();const migrar=Object.fromEntries($$('[data-migrate]').map(x=>[x.dataset.migrate,x.value]));S.config=await api('/api/etapas',{method:'PUT',body:{etapas:stages,migrar}});sincronizaEtapas();await carregaLeads();toast('Funil atualizado');location.hash='#/funil';};draw();
};
const funilOriginal=VIEWS.funil;
VIEWS.funil=()=>{funilOriginal();$('#page .ph').insertAdjacentHTML('beforeend','<a class="btn" href="#/etapas">Configurar etapas</a>');};

VIEWS.relatorios=()=>{
  crumbs([['Relatórios']]);
  const today=localDate(Date.now()/1000).slice(0,10);
  $('#page').innerHTML=`<div class="ph"><div><h1>Resultados comerciais</h1><p>Atividade, oportunidades e vendas por período e origem.</p></div></div><form class="card tbar" id="reportForm">${campo('inicio','De',today.slice(0,8)+'01','date','required')}${campo('fim','Até',today,'date','required')}<button class="btn pri">Atualizar relatório</button><button class="btn" type="button" id="reportExport" disabled>Exportar CSV</button></form><p class="hint section-gap">Contagens usam a data de cada evento; receita usa a data em que a oportunidade foi marcada como ganha. Valor em aberto é a carteira atual, sem filtro de período. Cada lead é atribuído à primeira busca de origem para evitar dupla contagem. Leads na lixeira não entram nos resultados. Respostas e reuniões referem-se às etapas originais correspondentes.</p><div id="reportResult" class="section-gap" aria-live="polite">Carregando…</div>`;
  let report=null,request=0;
  const load=async()=>{
    const current=++request;
    try{const result=await api('/api/relatorios?'+new URLSearchParams(dadosForm($('#reportForm'))));if(current!==request||!$('#reportResult'))return;report=result;
      const t=report.total;
      $('#reportResult').innerHTML=`<div class="grid g4">${[['Leads captados',fN(t.leads)],['Contatos realizados',fN(t.contatos)],['Vendas ganhas',fN(t.vendas)],['Receita ganha',reais(t.receita_centavos)]].map(([n,v])=>`<div class="card kpi"><div class="l">${n}</div><div class="n money">${v}</div></div>`).join('')}</div><div class="card section-gap">${tabelaComercial(['Origem','Leads','Contatos','Respostas','Reuniões','Oportunidades','Vendas','Receita ganha','Em aberto hoje'],report.origens.map(r=>[esc(r.origem),r.leads,r.contatos,r.respostas,r.reunioes,r.oportunidades,r.vendas,reais(r.receita_centavos),reais(r.aberto_centavos)]))}</div>`;
      $('#reportExport').disabled=false;
    }catch(err){if(current===request&&$('#reportResult'))$('#reportResult').textContent=err.message;}
  };
  $('#reportForm').onsubmit=e=>{e.preventDefault();load();};
  $('#reportExport').onclick=()=>{if(!report)return;downloadCsvComercial(['Origem','Leads','Contatos','Respostas','Reuniões','Oportunidades','Vendas','Receita (R$)','Em aberto (R$)'],report.origens.map(r=>[r.origem,r.leads,r.contatos,r.respostas,r.reunioes,r.oportunidades,r.vendas,(r.receita_centavos/100).toFixed(2),(r.aberto_centavos/100).toFixed(2)]),`relatorio_${report.inicio}_${report.fim}`);};load();
};
function downloadCsvComercial(headers,rows,name){
  const cell=v=>{let s=String(v??'');if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
  const url=URL.createObjectURL(new Blob(['\ufeff'+[headers,...rows].map(r=>r.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=name+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
VIEWS.lixeira=async()=>{
  crumbs([['Lixeira']]);
  $('#page').innerHTML='<div class="ph"><div><h1>Lixeira</h1><p>Restaure leads individualmente, incluindo histórico, tarefas e oportunidades. Buscas excluídas não são recriadas.</p></div></div><div class="card" id="trashRows" aria-live="polite">Carregando…</div>';
  const rows=await api('/api/lixeira');if(!$('#trashRows'))return;
  $('#trashRows').innerHTML=tabelaComercial(['Lead','Excluído em','Oportunidades','Tarefas','Ações'],rows.map(r=>[esc(r.nome),fData(r.excluido_em),r.oportunidades,r.tarefas,`<div class="row"><button class="btn sm" data-restore-lead="${r.id}">Restaurar</button><button class="btn sm danger" data-purge-lead="${r.id}">Excluir definitivamente</button></div>`]));
  $$('[data-restore-lead]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/lixeira/'+b.dataset.restoreLead+'/restaurar',{method:'POST',body:{}});await Promise.all([carregaLeads(),carregaBuscas()]);render();toast('Lead restaurado');}catch(err){b.disabled=false;mostraErro(err.message);}});
  $$('[data-purge-lead]').forEach(b=>b.onclick=async()=>{if(!await confirmar('Excluir definitivamente','O lead será removido da lixeira. Continuará bloqueado em novas buscas. Backups anteriores ainda poderão recuperá-lo.','Excluir definitivamente'))return;await api('/api/lixeira/'+b.dataset.purgeLead,{method:'DELETE'});render();toast('Lead removido da lixeira');});
};

iniciarCRM();
