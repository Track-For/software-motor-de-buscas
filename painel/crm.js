/* Fluxos do CRM, separados da renderização legada. */
let focoAnterior=null;
function mostraErro(msg){$('#errorText').textContent=msg;$('#errorBanner').hidden=false;}
window.addEventListener('unhandledrejection',e=>{e.preventDefault();mostraErro(e.reason?.message||'Não foi possível concluir a ação. Tente novamente.');});
$('#retryLoad').onclick=async()=>{ $('#errorBanner').hidden=true; await Promise.all([carregaLeads(),carregaBuscas()]);render(); };

function confirmar(titulo,texto,acao='Confirmar'){
  const d=$('#confirmDialog');
  if(d.open) return Promise.resolve(false);
  $('#confirmTitle').textContent=titulo;$('#confirmText').textContent=texto;$('#confirmYes').textContent=acao;
  return new Promise(resolve=>{
    const finish=v=>{d.close();resolve(v);};
    $('#confirmNo').onclick=()=>finish(false);$('#confirmYes').onclick=()=>finish(true);
    d.oncancel=e=>{e.preventDefault();finish(false);};d.showModal();$('#confirmNo').focus();
  });
}
let apagandoBuscas=false;
async function apagaBuscas(ids){
  if(!ids.length || apagandoBuscas)return;
  apagandoBuscas=true;
  try{
    if(!await confirmar('Excluir buscas',`Excluir ${ids.length} busca(s) e retirar todos os seus leads da base ativa, inclusive os presentes em outras buscas? Os leads irão para a Lixeira com histórico, tarefas e oportunidades. Buscas excluídas não são recuperadas pela lixeira. Um backup será salvo automaticamente.`,'Excluir buscas e leads'))return;
    let total=0;
    try{
      for(const id of ids){
        const r=await api(`/api/buscas/${id}`,{method:'DELETE'});
        total+=r.excluidos;buscasSelecionadas.delete(id);
      }
      toast(`Busca(s) excluída(s) com ${fN(total)} lead(s). Backup salvo.`);
    }finally{
      TB.sel.clear();
      await Promise.all([carregaLeads(),carregaBuscas()]);
      if(leadAberto&&!S.map[leadAberto.id])fechaLead();
      if(rota().v==='buscas' && rota().arg && !S.buscas.some(b=>b.id===rota().arg))location.hash='#/buscas';
      else render();
    }
  }catch(err){mostraErro('Não foi possível concluir a exclusão das buscas. '+err.message);}
  finally{apagandoBuscas=false;}
}
async function apagaLeads(ids){
  if(!ids.length)return;
  const texto=ids.length===1?`Excluir “${S.map[ids[0]]?.nome||'este lead'}” da base?`:`Excluir os ${fN(ids.length)} leads selecionados da base?`;
  if(!await confirmar('Excluir leads',texto+' Os leads irão para a Lixeira com histórico, tarefas e oportunidades preservados. Enquanto excluídos, não voltarão em novas buscas. Um backup completo será salvo automaticamente.','Excluir leads'))return;
  try{
    const r=await api('/api/leads/excluir',{method:'POST',body:{ids}});
    if(leadAberto&&ids.includes(leadAberto.id))fechaLead();
    TB.sel.clear();await Promise.all([carregaLeads(),carregaBuscas()]);render();toast(`${fN(r.excluidos)} lead(s) excluído(s). Backup salvo.`);
  }catch(err){mostraErro('Não foi possível excluir. '+err.message);}
}

function heroInicio(d){
  const retornos=S.leads.filter(l=>l.retorno&&l.retorno<=Date.now()/1000+86400&&!['fechado','descartado'].includes(l.status));
  const serie=d.contatos_dia||Array(7).fill(0),max=Math.max(1,...serie);
  const dias=serie.map((_,i)=>{const t=new Date();t.setDate(t.getDate()-6+i);return t.toLocaleDateString('pt-BR',{weekday:'short'}).replace('.','');});
  return `<section class="hero-grid"><div class="hero"><div class="eyebrow">Seu próximo negócio começa aqui</div><h2>Boas conexões.<br>Novas oportunidades.</h2><p>Encontre as empresas certas e dê o próximo passo em cada conversa.</p><a class="btn" href="#/nova">Explorar novos leads ${ic('trend')}</a><div class="orbit" aria-hidden="true"></div><div class="orbit-pin" aria-hidden="true">${ic('pin')}</div></div>
    <div class="card overview-card"><div class="eyebrow">Sua atividade · últimos 7 dias</div><div><strong class="num">${fN(d.contatos_semana)}</strong><p>contatos registrados</p></div><div class="mini-bars" role="img" aria-label="Contatos por dia: ${serie.join(', ')}">${serie.map((n,i)=>`<span style="height:${Math.max(4,n/max*100)}%" title="${dias[i]}: ${n} contato(s)"><small>${dias[i]}</small></span>`).join('')}</div><div class="overview-foot"><span>${retornos.length?`${fN(retornos.length)} retorno(s) nas próximas 24h`:'Mantenha suas conversas em dia'}</span><a href="#/agenda" aria-label="Abrir próximos contatos">${ic('trend')}</a></div></div></section>`;
}
function localDate(t){if(!t)return '';const d=new Date(t*1000);d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,16);}
function agendaCampos(l){
  return `<div class="card card-b" style="background:var(--surface-2);margin-bottom:18px"><label class="lbl" for="retorno" style="margin-top:0">Próximo contato</label><input class="in" id="retorno" type="datetime-local" value="${esc(localDate(l.retorno))}"><label class="lbl" for="motivoPerda">Motivo da perda (se houver)</label><input class="in" id="motivoPerda" maxlength="500" value="${esc(l.motivo_perda||'')}" placeholder="Ex.: sem orçamento neste momento"><div class="row" style="margin-top:12px;flex-wrap:wrap"><button class="btn sm pri" id="saveAgenda">Salvar acompanhamento</button>${l.retorno?'<button class="btn sm" id="clearAgenda">Concluir retorno</button>':''}</div></div><label class="lbl" for="canalContato">Já realizou o contato?</label><div class="row" style="margin-bottom:18px;flex-wrap:wrap"><select class="in" id="canalContato"><option value="whatsapp">WhatsApp</option><option value="ligacao">Ligação</option><option value="email">E-mail</option></select><button class="btn sm" id="confirmaContato">${ic('check')}Registrar contato realizado</button></div>`;
}
function conectaAgenda(l){
  const save=async clear=>{
    const value=$('#retorno').value;
    const retorno=clear||!value?null:new Date(value).getTime()/1000;
    if(retorno!==null&&!Number.isFinite(retorno))return toast('Informe uma data válida.');
    const novo=await api(`/api/leads/${encodeURIComponent(l.id)}`,{method:'PATCH',body:{retorno,motivo_perda:$('#motivoPerda').value}});
    upsertLead(novo);leadAberto=novo;desenhaLead();toast(clear?'Retorno concluído':'Acompanhamento salvo');
  };
  $('#saveAgenda').onclick=()=>save(false);if($('#clearAgenda'))$('#clearAgenda').onclick=()=>save(true);
  $('#confirmaContato').onclick=()=>registraEv($('#canalContato').value);
}
VIEWS.agenda=()=>{
  crumbs([['Próximos contatos']]);
  const rows=S.leads.filter(l=>l.retorno&&!['fechado','descartado'].includes(l.status)).sort((a,b)=>a.retorno-b.retorno);
  const now=Date.now()/1000;
  const groups=[['Pendentes',rows.filter(l=>l.retorno<now)],['Próximos retornos',rows.filter(l=>l.retorno>=now)]];
  $('#page').innerHTML=`<div class="ph"><div><h1>Cada conversa, no seu tempo.</h1><p>Seus retornos agendados, do mais próximo ao mais distante.</p></div><div class="acts"><a class="btn" href="#/leads">Ver todos os leads</a></div></div><div class="grid g2">${groups.map(([title,items])=>`<section class="card"><div class="card-h"><h3>${title}</h3><span class="pill nodot">${fN(items.length)}</span></div><div class="card-b">${items.length?items.map(l=>`<div class="agenda-row"><div class="agenda-avatar">${ic('phone')}</div><div class="agenda-info"><a href="#" data-lead="${esc(l.id)}"><b>${esc(l.nome)}</b></a><small>${esc(l.cidade)} · ${NOME_ST[l.status]}</small></div><div class="agenda-date">${fData(l.retorno)}</div></div>`).join(''):'<div class="agenda-empty">Nenhum retorno aqui. Abra a ficha de um lead para agendar o próximo contato.</div>'}</div></section>`).join('')}</div>`;
};
document.addEventListener('keydown',e=>{
  if(e.key!=='Tab'||!leadAberto||$('#confirmDialog').open)return;
  const items=$$('button:not(:disabled),a[href],input,select,textarea',$('#drawer')).filter(el=>el.offsetParent!==null);
  const first=items[0],last=items.at(-1);
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
});

function downloadJson(data){
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));a.download=`prospecta-backup-${new Date().toISOString().slice(0,10)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
const configOriginal=VIEWS.config;
VIEWS.config=async()=>{
  await configOriginal();if(rota().v!=='config')return;
  const page=$('#page');
  // Instruções correspondentes à plataforma, inclusive quando o motor estiver desligado.
  const win=/Win/i.test(navigator.platform);
  page.innerHTML=page.innerHTML.replaceAll('Prospeccao.command',win?'Iniciar.bat':'Prospeccao.command').replace('Baixar base completa (Excel)','Exportar leads (CSV para Excel)');
  $('#cExp').onclick=()=>exportaCsv(S.leads,'base-completa');
  const section=document.createElement('section');section.className='card';section.style.marginTop='18px';
  section.innerHTML=`<div class="card-h"><h3>Backup e restauração</h3></div><div class="card-b"><p class="muted sm">O backup completo inclui leads, histórico, retornos, extrações e mensagens. Cópias automáticas são salvas ao iniciar o painel e antes de exclusões ou restaurações.</p><div class="restore-actions"><button class="btn pri" id="backupDownload">${ic('down')}Baixar backup completo</button><button class="btn" id="backupUpload">Restaurar de arquivo</button><input type="file" id="backupFile" accept=".json,application/json" hidden></div><label class="lbl" for="backupList">Cópias locais</label><div class="row" style="flex-wrap:wrap"><select class="in" id="backupList" style="flex:1;min-width:0"><option value="">Carregando backups…</option></select><button class="btn" id="backupRestore">Restaurar cópia</button></div><p class="hint">A restauração substitui a base atual. Antes disso, uma cópia de segurança será criada. Buscas ativas precisam ser encerradas.</p></div>`;
  page.append(section);
  $('#backupDownload').onclick=async()=>downloadJson(await api('/api/backup'));
  $('#backupUpload').onclick=()=>$('#backupFile').click();
  const restore=async data=>{
    if(!await confirmar('Restaurar backup','A base atual será substituída pelo backup escolhido, incluindo histórico e mensagens. Uma cópia da base atual será salva antes de continuar.','Restaurar backup'))return;
    await api('/api/restaurar',{method:'POST',body:data});await Promise.all([carregaLeads(),carregaBuscas(),api('/api/config').then(c=>S.config=c)]);toast('Backup restaurado');render();
  };
  $('#backupFile').onchange=async e=>{
    const file=e.target.files[0];if(!file)return;
    try{if(file.size>50*1024*1024)throw Error('O limite é 50 MB.');await restore(JSON.parse(await file.text()));}catch(err){mostraErro('Falha ao restaurar: '+err.message);}finally{e.target.value='';}
  };
  $('#backupRestore').onclick=()=>{const arquivo=$('#backupList').value;if(arquivo)return restore({arquivo});toast('Selecione uma cópia.');};
  const backups=await api('/api/backups');if(!$('#backupList'))return;
  $('#backupList').innerHTML=backups.length?backups.map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join(''):'<option value="">Nenhuma cópia local</option>';
};

async function iniciarCRM(){
  await Promise.all([carregaBuscas(),carregaLeads(),status(),api('/api/config').then(c=>S.config=c).catch(err=>mostraErro('Não foi possível carregar as mensagens. '+err.message))]);
  render();
  let ticking=false;setInterval(async()=>{if(ticking)return;ticking=true;try{await tick();}finally{ticking=false;}},3000);
  let checking=false;setInterval(async()=>{if(checking)return;checking=true;try{await status();}finally{checking=false;}},15000);
}
