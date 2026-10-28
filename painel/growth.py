"""Priorização e ferramentas comerciais locais. Nunca envia mensagens."""
import copy
import datetime as dt
import time
import re
import uuid
import urllib.parse

import business as biz
import site_audit
import threading

AUDIT_SLOTS = threading.BoundedSemaphore(2)

OFFERS = {'site': 'Site', 'whatsapp': 'Agente de WhatsApp com IA', 'ambos': 'Site e agente de WhatsApp com IA', 'investigar': 'Diagnóstico inicial'}
CHANNELS = ('whatsapp', 'email', 'ligacao')


def blocked(lead):
    return bool(lead.get('nao_contatar')) or lead.get('status') in ('fechado', 'descartado')


def ranking(lead, now=None):
    now = now or time.time()
    if blocked(lead):
        return None
    reasons, score = [], 0
    def add(points, reason):
        nonlocal score
        score += points
        reasons.append({'pontos': points, 'motivo': reason})
    if not lead.get('site'):
        add(20, 'Sem site cadastrado')
    if lead.get('whatsapp'):
        add(15, 'WhatsApp disponível')
    elif lead.get('email') or lead.get('telefone'):
        add(8, 'Outro canal de contato disponível')
    rec = biz.recomendar(lead)
    if rec['oferta'] in ('whatsapp', 'ambos'):
        add(10, 'Indicação de potencial para agente de WhatsApp')
    if any(o['estado'] == 'aberta' for o in lead.get('oportunidades', [])):
        add(25, 'Oportunidade em aberto')
    if lead.get('retorno') and lead['retorno'] <= now:
        add(25, 'Retorno vencido ou para agora')
    elif any(not t['concluida'] and not t.get('cancelada') and t['prazo'] <= now for t in lead.get('tarefas', [])):
        add(20, 'Tarefa pendente vencida')
    last = lead.get('ultimo_contato')
    if not last:
        add(15, 'Ainda sem contato registrado')
    elif now - last >= 7 * 86400:
        add(15, 'Há pelo menos 7 dias sem contato')
    elif now - last < 86400:
        add(-20, 'Contato registrado nas últimas 24 horas')
    priority = {'alta': 10, 'urgente': 20, 'baixa': -10}.get(lead.get('prioridade'), 0)
    if priority:
        add(priority, 'Prioridade definida na ficha: '+lead['prioridade'])
    return dict(id=lead['id'], nome=lead['nome'], categoria=lead.get('categoria', ''), cidade=lead.get('cidade', ''),
                pontos=max(0, score), motivos=reasons, oferta=rec['oferta'], confianca=rec['confianca'])


def draft(lead, offer, style):
    if offer not in OFFERS or style not in ('consultiva', 'direta'):
        raise ValueError('Oferta ou abordagem inválida.')
    intro = f"Olá, equipe da {lead['nome']}! "
    question = {'site': 'Vocês já têm um site próprio para apresentar os serviços e receber contatos?',
                'whatsapp': 'Vocês recebem perguntas repetitivas ou pedidos de agendamento pelo WhatsApp?',
                'ambos': 'Como vocês apresentam os serviços online e organizam os contatos que chegam pelo WhatsApp?',
                'investigar': 'Como vocês recebem novos clientes hoje?'}[offer]
    pitch = {'site': 'Trabalho com criação e melhoria de sites para empresas.',
             'whatsapp': 'Trabalho com agentes de WhatsApp com IA para apoiar o atendimento.',
             'ambos': 'Trabalho com sites e agentes de WhatsApp com IA para apoiar a captação e o atendimento.',
             'investigar': 'Posso ajudar a avaliar a presença online e a rotina de atendimento.'}[offer]
    evidence = ''
    audit = lead.get('diagnostico', {})
    if audit.get('url') == lead.get('site') and audit.get('estado') == 'concluido' and time.time()-audit.get('verificado_em', 0) < 30*86400:
        broken = next((x for x in audit.get('links', []) if x['estado'] == 'quebrado'), None)
        if broken and offer in ('site', 'ambos'):
            evidence = f" Na verificação de {dt.datetime.fromtimestamp(audit['verificado_em']).strftime('%d/%m/%Y')}, o link {broken['url']} respondeu HTTP {broken['http']}. Podemos conferir juntos?"
    return intro + (question+' '+pitch if style == 'consultiva' else pitch+' '+question) + evidence + ' Faz sentido conversarmos?'


def save_approach(lead, d):
    if blocked(lead):
        raise ValueError('Lead encerrado ou marcado para não receber contato.')
    offer, style = d.get('oferta'), d.get('estilo', 'consultiva')
    generated = draft(lead, offer, style)
    message = biz.texto(d.get('texto', generated), 4000, True)
    rows = lead.setdefault('abordagens', [])
    if len(rows) >= 100:
        raise ValueError('Limite de 100 abordagens por lead.')
    item = dict(id=uuid.uuid4().hex, oferta=offer, estilo=style, texto=message, criado_em=time.time())
    rows.append(item)
    return item


def stop_sequence(lead, reason):
    seq = lead.get('sequencia')
    if not seq or seq.get('estado') not in ('ativa', 'aguardando_contato'):
        return
    seq.update(estado='interrompida', motivo=reason, encerrado_em=time.time())
    for task in lead.get('tarefas', []):
        if task.get('sequencia_id') == seq['id'] and not task['concluida']:
            task['cancelada'] = True


def schedule(lead, anchor):
    seq = lead['sequencia']
    if blocked(lead) or lead.get('status') in ('respondeu', 'reuniao'):
        raise ValueError('A sequência exige um lead aberto e sem resposta registrada.')
    if len(lead.get('tarefas', [])) > 997:
        raise ValueError('Limite de tarefas atingido.')
    seq.update(estado='ativa', inicio=anchor)
    for day in (3, 7, 14):
        task = biz.tarefa({'titulo': f'Retorno da sequência — dia {day}', 'prazo': anchor+day*86400})
        task['sequencia_id'] = seq['id']
        lead.setdefault('tarefas', []).append(task)


def on_event(lead, event):
    """Executado pelo registro central, inclusive para mudanças em lote."""
    if event['tipo'] == 'status' and lead.get('status') in ('respondeu', 'reuniao', 'fechado', 'descartado'):
        stop_sequence(lead, 'Etapa alterada: '+lead['status'])
    if event['tipo'] in CHANNELS:
        event.update(segmento=lead.get('categoria') or 'Não informado', cidade=lead.get('cidade') or 'Não informada')
        seq = lead.get('sequencia', {})
        if seq.get('estado') == 'aguardando_contato' and not blocked(lead):
            try:
                schedule(lead, event['t'])
            except ValueError:
                stop_sequence(lead, 'Não foi possível criar lembretes; confira a etapa e o limite de tarefas.')
        elif seq.get('estado') == 'ativa':
            for task in lead.get('tarefas', []):
                if task.get('sequencia_id') == seq['id'] and not task['concluida'] and task['prazo'] <= event['t']:
                    task.update(concluida=True, concluido_em=event['t'])


def sequence_view(lead):
    seq = copy.deepcopy(lead.get('sequencia', {}))
    if seq.get('estado') == 'ativa' and not any(not t['concluida'] and not t.get('cancelada') for t in lead.get('tarefas', []) if t.get('sequencia_id') == seq['id']):
        seq['estado'] = 'concluida'
    return seq


def conversions(app, query):
    today = dt.date.today()
    start = dt.date.fromisoformat(query.get('inicio', [today.replace(day=1).isoformat()])[0])
    end = dt.date.fromisoformat(query.get('fim', [today.isoformat()])[0])
    if start > end or end.year > 2999 or (end-start).days > 3660:
        raise ValueError('Período inválido; limite de 10 anos.')
    begin = dt.datetime.combine(start, dt.time()).timestamp()
    finish = dt.datetime.combine(end+dt.timedelta(days=1), dt.time()).timestamp()
    dimension = query.get('agrupar', ['segmento'])[0]
    if dimension not in ('segmento', 'cidade', 'oferta', 'abordagem'):
        raise ValueError('Agrupamento inválido.')
    groups = {}
    for lead in app.leads.values():
        contacts = sorted((e for e in lead.get('historico', []) if e['tipo'] in CHANNELS), key=lambda e:e['t'])
        if not contacts or not begin <= contacts[0]['t'] < finish:
            continue
        first = contacts[0]
        value = first.get(dimension) or 'Sem atribuição registrada'
        key = OFFERS.get(value, value) if dimension == 'oferta' else value
        row = groups.setdefault(key, dict(grupo=key, contatados=0, respostas=0, reunioes=0, clientes=0, receita_centavos=0))
        events = [e for e in lead.get('historico', []) if first['t'] <= e['t'] < finish]
        statuses = {e.get('status') for e in events}
        row['contatados'] += 1
        row['respostas'] += int(any(e['tipo'] == 'resposta' for e in events) or 'respondeu' in statuses)
        row['reunioes'] += int('reuniao' in statuses)
        won = [o for o in lead.get('oportunidades', []) if o['estado'] == 'ganha' and first['t'] <= (o.get('fechado_em') or 0) < finish]
        row['clientes'] += int(bool(won) or 'fechado' in statuses)
        row['receita_centavos'] += sum(o['valor_centavos'] for o in won)
    for row in groups.values():
        for field in ('respostas', 'reunioes', 'clientes'):
            row['taxa_'+field] = round(100*row[field]/row['contatados'], 1)
    return dict(inicio=start.isoformat(), fim=end.isoformat(), agrupar=dimension,
                grupos=sorted(groups.values(), key=lambda r:(-r['clientes'], -r['respostas'], -r['contatados'], r['grupo'])))


def proposal(d, old=None):
    old = old or {}
    return dict(id=old.get('id', uuid.uuid4().hex), servico=biz.texto(d.get('servico'), 200, True),
                escopo=biz.texto(d.get('escopo'), 8000, True), valor_centavos=biz.centavos(d.get('valor')),
                prazo=biz.texto(d.get('prazo'), 200, True), validade=biz.data(d.get('validade')),
                condicoes=biz.texto(d.get('condicoes', ''), 3000), estado='rascunho', criado_em=old.get('criado_em', time.time()))


def transition_proposal(app, lead, item, state):
    if state == item['estado']:
        return
    allowed = {'rascunho': ('enviada',), 'enviada': ('aceita', 'recusada')}
    if state not in allowed.get(item['estado'], ()):
        raise ValueError('Transição de proposta inválida.')
    if state == 'enviada':
        if blocked(lead):
            raise ValueError('Lead encerrado ou marcado para não receber contato.')
        if len(lead.get('tarefas', [])) >= 1000:
            raise ValueError('Limite de tarefas atingido.')
        task = biz.tarefa({'titulo': 'Retorno da proposta: '+item['servico'][:170], 'prazo': time.time()+3*86400})
        task['proposta_id'] = item['id']
        lead.setdefault('tarefas', []).append(task)
        item['enviado_em'] = time.time()
    else:
        if state == 'aceita':
            if len(lead.get('oportunidades', [])) >= 1000:
                raise ValueError('Limite de oportunidades atingido.')
            op = biz.oportunidade({'servico': item['servico'], 'valor': str(biz.Decimal(item['valor_centavos'])/100), 'estado': 'ganha'})
            op['proposta_id'] = item['id']
            lead.setdefault('oportunidades', []).append(op)
            lead['status'] = 'fechado'
            app.registrar(lead, 'status', 'Status: '+biz.nomes_etapas(app)['fechado'])
        for task in lead.get('tarefas', []):
            if task.get('proposta_id') == item['id'] and not task['concluida']:
                task.update(concluida=True, concluido_em=time.time())
        item['respondido_em'] = time.time()
        stop_sequence(lead, 'Resposta à proposta: '+state)
    item['estado'] = state


def validate(lead):
    """Valida campos novos também em backups e na lixeira."""
    if type(lead.get('nao_contatar', False)) is not bool:
        raise ValueError('Preferência de contato inválida.')
    for group, limit in (('abordagens', 100), ('propostas', 100)):
        rows = lead.get(group, [])
        if not isinstance(rows, list) or len(rows) > limit:
            raise ValueError('Registros de aquisição inválidos.')
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not re.fullmatch(r'[\w-]+', row['id']) or row['id'] in seen:
                raise ValueError('Registro de aquisição inválido.')
            seen.add(row['id']); biz.timestamp(row.get('criado_em'))
            if group == 'abordagens':
                if row.get('oferta') not in OFFERS or row.get('estilo') not in ('consultiva', 'direta'):
                    raise ValueError('Abordagem inválida.')
                biz.texto(row.get('texto'), 4000, True)
            else:
                cents = row.get('valor_centavos')
                if type(cents) is not int or cents < 0 or row.get('estado') not in ('rascunho', 'enviada', 'aceita', 'recusada'):
                    raise ValueError('Proposta inválida.')
                proposal(row | {'valor': str(biz.Decimal(cents)/100)}, row)
                for key in ('enviado_em', 'respondido_em'):
                    if key in row:
                        biz.timestamp(row[key])
    seq = lead.get('sequencia')
    if seq is not None:
        if not isinstance(seq, dict) or not re.fullmatch(r'[\w-]+', str(seq.get('id', ''))) or seq.get('estado') not in ('ativa', 'aguardando_contato', 'concluida', 'interrompida'):
            raise ValueError('Sequência inválida.')
        biz.timestamp(seq.get('criado_em'))
        for key in ('inicio', 'encerrado_em'):
            if key in seq:
                biz.timestamp(seq[key])
    audit = lead.get('diagnostico')
    if audit is not None:
        if not isinstance(audit, dict) or audit.get('estado') not in ('concluido', 'inconclusivo'):
            raise ValueError('Diagnóstico inválido.')
        biz.texto(audit.get('url'), 2000, True); biz.timestamp(audit.get('verificado_em'))
        biz.texto(audit.get('resumo'), 1000)
        for key in ('verificacoes', 'links'):
            if not isinstance(audit.get(key), list) or len(audit[key]) > 10:
                raise ValueError('Diagnóstico inválido.')
        for check in audit['verificacoes']:
            if not isinstance(check, dict) or type(check.get('encontrado')) is not bool:
                raise ValueError('Verificação inválida.')
            biz.texto(check.get('nome'), 200); biz.texto(check.get('id'), 80)
        for link in audit['links']:
            if not isinstance(link, dict) or link.get('estado') not in ('ok', 'quebrado', 'inconclusivo'):
                raise ValueError('Link inválido.')
            biz.texto(link.get('url'), 2000, True)
            if link.get('http') is not None and (type(link['http']) is not int or not 100 <= link['http'] <= 599):
                raise ValueError('Status HTTP inválido.')
    for task in lead.get('tarefas', []):
        if type(task.get('cancelada', False)) is not bool:
            raise ValueError('Cancelamento de tarefa inválido.')


def dispatch(h, app):
    path, method = h._rota(), h.command
    m = re.fullmatch(r'/api/leads/([\w-]+)/propostas(?:/([\w-]+))?', path)
    if m and method in ('POST', 'PATCH'):
        with app.lock:
            lead = app.leads.get(m[1])
            if lead is None:
                h._envia(404, {'erro': 'Lead não encontrado.'}); return True
            d = h._corpo()
            rows = lead.setdefault('propostas', [])
            old = next((p for p in rows if p['id'] == m[2]), None)
            if m[2] and old is None:
                h._envia(404, {'erro': 'Proposta não encontrada.'}); return True
            if method == 'PATCH' and old is not None:
                if 'estado' in d:
                    transition_proposal(app, lead, old, d['estado'])
                elif old['estado'] == 'rascunho':
                    updated = proposal(old | {'valor': str(biz.Decimal(old['valor_centavos'])/100)} | d, old)
                    old.clear(); old.update(updated)
                else:
                    raise ValueError('Somente rascunhos podem ser editados.')
            elif method == 'POST' and not m[2]:
                if len(rows) >= 100:
                    raise ValueError('Limite de 100 propostas por lead.')
                item = proposal(d); rows.append(item)
            else:
                raise ValueError('Operação inválida.')
            app.registrar(lead, 'proposta', 'Proposta '+(old['estado'] if old else 'criada'))
            app.persistir(); h._envia(200, lead)
        return True
    if path == '/api/conversoes' and method == 'GET':
        with app.lock:
            h._envia(200, conversions(app, urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)))
        return True
    m = re.fullmatch(r'/api/leads/([\w-]+)/(sequencia|resposta|preferencia-contato|contato-comercial)', path)
    if m and method == 'POST':
        with app.lock:
            lead = app.leads.get(m[1])
            if lead is None:
                h._envia(404, {'erro': 'Lead não encontrado.'}); return True
            d, action = h._corpo(), m[2]
            if action == 'sequencia':
                if d.get('acao') == 'parar':
                    stop_sequence(lead, 'Interrompida manualmente')
                elif d.get('acao') == 'iniciar':
                    if blocked(lead) or lead.get('status') in ('respondeu', 'reuniao'):
                        raise ValueError('Lead encerrado, com resposta ou bloqueado para contato.')
                    if sequence_view(lead).get('estado') in ('ativa', 'aguardando_contato'):
                        raise ValueError('Já existe uma sequência ativa.')
                    if len(lead.get('tarefas', [])) > 997:
                        raise ValueError('Limite de tarefas atingido.')
                    lead['sequencia'] = dict(id=uuid.uuid4().hex, estado='aguardando_contato', criado_em=time.time())
                    if lead.get('ultimo_contato'):
                        schedule(lead, lead['ultimo_contato'])
                else:
                    raise ValueError('Ação inválida.')
                app.registrar(lead, 'sequencia', 'Sequência de lembretes: '+lead['sequencia']['estado'] if lead.get('sequencia') else 'Sem sequência')
            elif action == 'preferencia-contato':
                if type(d.get('nao_contatar')) is not bool:
                    raise ValueError('Preferência inválida.')
                lead['nao_contatar'] = d['nao_contatar']
                if lead['nao_contatar']:
                    stop_sequence(lead, 'Pedido para não receber contato')
                app.registrar(lead, 'preferencia', 'Não contatar' if lead['nao_contatar'] else 'Contato liberado manualmente')
            elif action == 'resposta':
                app.registrar(lead, 'resposta', biz.texto(d.get('nota', 'Resposta recebida'), 1000, True))
                stop_sequence(lead, 'Resposta recebida')
                if lead['status'] not in ('fechado', 'descartado') and 'respondeu' in biz.nomes_etapas(app):
                    lead['status'] = 'respondeu'; app.registrar(lead, 'status', 'Status: '+biz.nomes_etapas(app)['respondeu'])
            else:
                if blocked(lead):
                    raise ValueError('Lead encerrado ou marcado para não receber contato.')
                channel = d.get('canal')
                approach = next((a for a in lead.get('abordagens', []) if a['id'] == d.get('abordagem_id')), None)
                if channel not in CHANNELS or approach is None:
                    raise ValueError('Escolha canal e abordagem salva.')
                app.registrar(lead, channel, 'Contato realizado com abordagem revisada')
                lead['historico'][-1].update(oferta=approach['oferta'], abordagem=approach['estilo'], abordagem_id=approach['id'])
                if lead['status'] == 'novo' and app.config.get('auto_contatado', True):
                    lead['status'] = 'contatado'; app.registrar(lead, 'status', 'Status: '+biz.nomes_etapas(app)['contatado'])
            app.persistir(); h._envia(200, lead)
        return True
    m = re.fullmatch(r'/api/leads/([\w-]+)/abordagens', path)
    if m and method == 'POST':
        with app.lock:
            lead = app.leads.get(m[1])
            if lead is None:
                h._envia(404, {'erro': 'Lead não encontrado.'}); return True
            d = h._corpo()
            if d.get('previa') is True:
                if blocked(lead):
                    raise ValueError('Lead encerrado ou marcado para não receber contato.')
                h._envia(200, {'texto': draft(lead, d.get('oferta'), d.get('estilo', 'consultiva'))})
            else:
                save_approach(lead, d)
                app.registrar(lead, 'abordagem', 'Rascunho de abordagem salvo; nenhum envio realizado')
                app.persistir(); h._envia(200, lead)
        return True
    m = re.fullmatch(r'/api/leads/([\w-]+)/diagnostico', path)
    if m and method == 'POST':
        with app.lock:
            lead = app.leads.get(m[1])
            if lead is None:
                h._envia(404, {'erro': 'Lead não encontrado.'}); return True
            url = lead.get('site', '')
            if not url:
                raise ValueError('Este lead não tem site cadastrado.')
        if not AUDIT_SLOTS.acquire(blocking=False):
            h._envia(409, {'erro': 'Há dois diagnósticos em andamento. Tente novamente em instantes.'}); return True
        try:
            result = site_audit.analyze(url)
        finally:
            AUDIT_SLOTS.release()
        with app.lock:
            lead = app.leads.get(m[1])
            if lead is None or lead.get('site') != url:
                h._envia(409, {'erro': 'O lead ou site mudou durante a análise. Abra a ficha novamente.'}); return True
            lead['diagnostico'] = result
            app.registrar(lead, 'diagnostico', 'Diagnóstico do site: '+result['estado'])
            app.persistir(); h._envia(200, lead)
        return True
    if path == '/api/prioridades' and method == 'GET':
        with app.lock:
            rows = [r for l in app.leads.values() if (r := ranking(l)) is not None]
            rows.sort(key=lambda r: (-r['pontos'], r['nome'].casefold(), r['id']))
            h._envia(200, rows)
        return True
    return False
