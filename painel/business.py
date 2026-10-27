"""Regras comerciais do CRM. Valores monetários são armazenados em centavos."""
import copy
import csv
import datetime as dt
import io
import math
import re
import time
import unicodedata
import urllib.parse
import uuid
from decimal import Decimal, InvalidOperation


def texto(value, limit=200, required=False):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'Texto inválido (máximo {limit} caracteres).')
    value = value.strip()
    if required and not value:
        raise ValueError('Preencha os campos obrigatórios.')
    return value


def data(value):
    if not value:
        return ''
    value = texto(value, 10)
    dt.date.fromisoformat(value)
    return value


def timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value < 32503680000:
        raise ValueError('Data inválida.')
    return value


def centavos(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > Decimal('999999999.99') or number != number.quantize(Decimal('.01')):
            raise ValueError('Valor inválido. Use até duas casas decimais.')
        return int(number * 100)
    except InvalidOperation as exc:
        raise ValueError('Informe um valor monetário válido.') from exc


def oportunidade(d, old=None):
    old = old or {}
    state = d.get('estado', 'aberta')
    if state not in ('aberta', 'ganha', 'perdida'):
        raise ValueError('Situação da oportunidade inválida.')
    closed = old.get('fechado_em') if old.get('estado') == state else None
    return dict(id=old.get('id', uuid.uuid4().hex), servico=texto(d.get('servico'), 200, True),
                valor_centavos=centavos(d.get('valor')), previsao=data(d.get('previsao')),
                estado=state, criado_em=old.get('criado_em', time.time()),
                fechado_em=(closed or time.time()) if state != 'aberta' else None,
                atualizado_em=time.time())


def tarefa(d, old=None):
    old = old or {}
    done = d.get('concluida', False)
    if not isinstance(done, bool):
        raise ValueError('Conclusão inválida.')
    return dict(id=old.get('id', uuid.uuid4().hex), titulo=texto(d.get('titulo'), 200, True),
                prazo=timestamp(d.get('prazo')), concluida=done,
                criado_em=old.get('criado_em', time.time()),
                concluido_em=(old.get('concluido_em') or time.time()) if done else None)


CONTACT_FIELDS = ('nome', 'categoria', 'telefone', 'whatsapp', 'email', 'site', 'cidade', 'uf', 'bairro', 'endereco', 'cep', 'instagram', 'facebook', 'linkedin')


def contatos(app, d, original=None):
    lead = copy.deepcopy(original) if original else app.lead_de({'place_id': 'm' + uuid.uuid4().hex})
    for field in CONTACT_FIELDS:
        if field in d:
            lead[field] = texto(d[field], 500)
    texto(lead.get('nome'), 500, True)
    for field in ('site', 'instagram', 'facebook', 'linkedin'):
        value = lead.get(field, '')
        if value:
            if not re.match(r'^https?://', value, re.I):
                value = 'https://' + value
            parsed = urllib.parse.urlparse(value)
            if not parsed.hostname or any(c.isspace() for c in value) or ':' in parsed.hostname:
                raise ValueError('Endereço de site inválido.')
            lead[field] = value
    if lead.get('email'):
        emails = [v.strip() for v in re.split(r'[,;]', lead['email']) if v.strip()]
        if not emails or any(not re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+', v) for v in emails):
            raise ValueError('E-mail inválido. Separe vários endereços por vírgula.')
        lead['email'] = ', '.join(dict.fromkeys(emails))
    if 'telefone' in d or not original:
        lead['tel_digitos'], lead['tel_tipo'] = app.telefone_br(lead.get('telefone', ''))
    if 'whatsapp' in d:
        lead['whatsapp'] = re.sub(r'\D', '', d['whatsapp'])
        if lead['whatsapp'] and len(lead['whatsapp']) in (10, 11):
            lead['whatsapp'] = '55' + lead['whatsapp']
        if lead['whatsapp'] and not 10 <= len(lead['whatsapp']) <= 15:
            raise ValueError('WhatsApp inválido. Use DDD e número.')
        lead['whatsapp_origem'] = 'manual'
    if not original:
        now = time.time()
        lead.update(status='novo', obs='', buscas=[], historico=[], criado_em=now, atualizado_em=now, ultimo_contato=None, nicho='Cadastro manual')
    lead['campos_editados'] = sorted(set(lead.get('campos_editados', [])) | set(d).intersection(CONTACT_FIELDS))
    return lead


def normal(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c)).strip()


def duplicado(lead, rows):
    for other in rows:
        if (lead.get('tel_digitos') and lead['tel_digitos'] == other.get('tel_digitos')) or (lead.get('email') and lead['email'].lower() == other.get('email', '').lower()) or (normal(lead['nome']) == normal(other['nome']) and normal(lead.get('cidade', '')) == normal(other.get('cidade', ''))):
            return other
    return None


def importar(app, d):
    source = d.get('csv')
    texto(source, 5_000_000, True)
    source = source.lstrip('\ufeff')
    delimiter = d.get('separador', ';')
    if delimiter not in (',', ';', '\t'):
        raise ValueError('Separador inválido.')
    reader = csv.DictReader(io.StringIO(source), delimiter=delimiter, strict=True)
    headers = reader.fieldnames or []
    if len(set(headers)) != len(headers):
        raise ValueError('O CSV contém cabeçalhos repetidos.')
    aliases = {'empresa':'nome', 'name':'nome', 'categoria':'categoria', 'telefone':'telefone', 'whatsapp':'whatsapp', 'e-mail':'email', 'email':'email', 'site':'site', 'cidade':'cidade', 'uf':'uf', 'bairro':'bairro', 'endereco':'endereco', 'cep':'cep', 'nome':'nome'}
    mapping = d.get('mapeamento') or {aliases[normal(h)]: h for h in headers if normal(h) in aliases}
    if not isinstance(mapping, dict) or any(k not in CONTACT_FIELDS or v not in headers for k, v in mapping.items()):
        raise ValueError('Mapeamento de colunas inválido.')
    if 'nome' not in mapping:
        return {'colunas': headers, 'mapeamento': mapping, 'linhas': [], 'validos': 0, 'duplicados': 0, 'erros': 0, 'precisa_mapear': True}, []
    valid, results = [], []
    existing = list(app.leads.values()) + [x['lead'] for x in app.lixeira.values()]
    for index, row in enumerate(reader, 2):
        if index > 5001:
            raise ValueError('Importe no máximo 5.000 linhas por vez.')
        try:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Quantidade de colunas diferente do cabeçalho.')
            lead = contatos(app, {k: row[v] for k, v in mapping.items()})
            duplicate = duplicado(lead, existing + valid)
            state = 'duplicado' if duplicate else 'válido'
            if not duplicate:
                lead['nicho'] = 'Importação CSV'
                valid.append(lead)
            results.append({'linha': index, 'nome': lead['nome'], 'estado': state, 'mensagem': 'Já existe na base ou na lixeira.' if duplicate else ''})
        except ValueError as exc:
            results.append({'linha': index, 'nome': row.get(mapping['nome'], ''), 'estado': 'erro', 'mensagem': str(exc)})
    return {'colunas': headers, 'mapeamento': mapping, 'linhas': results, 'validos': len(valid), 'duplicados': sum(r['estado'] == 'duplicado' for r in results), 'erros': sum(r['estado'] == 'erro' for r in results)}, valid


def etapas(app, cfg=None):
    cfg = app.config if cfg is None else cfg
    colors = ['#64748b', '#006bf5', '#a16207', '#7054b8', '#218347', '#c42f37']
    return cfg.get('etapas') or [dict(id=k, nome=app.NOME_STATUS[k], cor=c) for k, c in zip(app.STATUS_LEAD, colors)]


def validar_etapas(rows):
    if not isinstance(rows, list) or not 4 <= len(rows) <= 20:
        raise ValueError('Use de 4 a 20 etapas.')
    ids = []
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', row.get('id', '')) or not re.fullmatch(r'#[0-9a-fA-F]{6}', row.get('cor', '')):
            raise ValueError('Etapa inválida.')
        texto(row.get('nome'), 60, True)
        ids.append(row['id'])
    if len(ids) != len(set(ids)) or not {'novo', 'contatado', 'fechado', 'descartado'} <= set(ids):
        raise ValueError('Mantenha as etapas de entrada, contato, ganho e descarte, com IDs únicos.')
    return rows


def nomes_etapas(app, cfg=None):
    return {r['id']: r['nome'] for r in etapas(app, cfg)}


def organizacao(d):
    tags, priority = d.get('tags', []), d.get('prioridade', 'normal')
    if not isinstance(tags, list) or len(tags) > 20 or priority not in ('baixa', 'normal', 'alta', 'urgente'):
        raise ValueError('Tags ou prioridade inválidas.')
    return {'tags': list(dict.fromkeys(texto(t, 40, True) for t in tags)), 'prioridade': priority}


FILTER_KEYS = {'texto', 'status', 'cidade', 'categoria', 'tag', 'prioridade', 'busca', 'wa', 'email', 'semsite', 'nota4', 'ocultarFechados', 'ocultarDescartados'}
BOOL_FILTERS = {'wa', 'email', 'semsite', 'nota4', 'ocultarFechados', 'ocultarDescartados'}


def validar_filtro(d):
    if not isinstance(d, dict) or any(k not in FILTER_KEYS for k in d):
        raise ValueError('Filtro inválido.')
    for k, v in d.items():
        if k in BOOL_FILTERS:
            if not isinstance(v, bool):
                raise ValueError('Filtro inválido.')
        else:
            texto(v, 500)
    return d


def qualificacao(d):
    if not isinstance(d, dict):
        raise ValueError('Qualificação inválida.')
    choices = {'site': ('desconhecido', 'ausente', 'problemas', 'adequado'),
               'usa_whatsapp': ('desconhecido', 'sim', 'nao'),
               'repetitivas': ('desconhecido', 'sim', 'nao'),
               'agendamentos': ('desconhecido', 'sim', 'nao'),
               'perde_contatos': ('desconhecido', 'sim', 'nao')}
    if set(d) - (set(choices) | {'mensagens_dia'}):
        raise ValueError('Campo de qualificação inválido.')
    result = {}
    for key, options in choices.items():
        value = d.get(key, 'desconhecido')
        if value not in options:
            raise ValueError('Resposta de qualificação inválida.')
        result[key] = value
    count = d.get('mensagens_dia')
    if count is not None and (type(count) is not int or not 0 <= count <= 1000000):
        raise ValueError('Informe um número inteiro de mensagens por dia, ou deixe vazio.')
    result['mensagens_dia'] = count
    return result


def recomendar(lead):
    q = qualificacao(lead.get('qualificacao', {}))
    reasons, pending = [], []
    site = q['site'] in ('ausente', 'problemas')
    site_confirmed = site
    if site:
        reasons.append('Informado na qualificação: ' + ('não possui site próprio.' if q['site'] == 'ausente' else 'site apresenta problemas verificados.'))
    elif q['site'] == 'desconhecido':
        url = lead.get('site', '')
        host = (urllib.parse.urlparse(url if '://' in url else '//'+url).hostname or '').lower()
        social = any(host == domain or host.endswith('.'+domain) for domain in ('instagram.com', 'facebook.com', 'wa.me', 'whatsapp.com', 'linktr.ee'))
        if not url or social:
            site = True
            reasons.append('O cadastro não informa site próprio.' if not url else 'O endereço cadastrado leva a rede social, WhatsApp ou página de links.')
            pending.append('Confirmar se a empresa já possui site próprio.')
        else:
            pending.append('Verificar a qualidade do site; o painel não faz auditoria automática.')
    uses = q['usa_whatsapp'] == 'sim' or (q['usa_whatsapp'] == 'desconhecido' and bool(lead.get('whatsapp')))
    needs = [label for field, label in [('repetitivas', 'perguntas repetitivas'), ('agendamentos', 'solicitações de agendamento'), ('perde_contatos', 'perda de contatos por demora ou fora do horário')] if q[field] == 'sim']
    agent = uses and bool(needs)
    agent_confirmed = agent and q['usa_whatsapp'] == 'sim'
    category = normal(lead.get('categoria', ''))
    # Heurística de prospecção, não comprovação de demanda ou de volume.
    segment = next((label for pattern, label in (
        (r'psicolog|dentist|odont|clinic|terapeut|medic|fisioterap', 'consultas e agendamentos'),
        (r'advog|juridic|contab', 'triagem inicial e marcação de atendimento'),
        (r'escola|idioma|ingles|curso', 'informações sobre cursos, horários e matrículas'),
        (r'estetic|beleza|salao|barbear|cabeleir', 'serviços, preços e agendamentos'),
        (r'oficina|mecanic|assistencia tecnica', 'pedidos de orçamento e acompanhamento'),
        (r'hotel|pousada', 'informações de hospedagem e reservas'),
    ) if re.search(pattern, category)), None)
    inferred = (not agent and uses and segment is not None
                and any(q[k] == 'desconhecido' for k in ('repetitivas', 'agendamentos', 'perde_contatos'))
                and q['mensagens_dia'] != 0)
    if inferred:
        agent = True
        reasons.append(f"Hipótese pelo segmento cadastrado ({lead.get('categoria', '')}): avaliar automação de {segment}.")
        reasons.append('Uso de WhatsApp informado na qualificação.' if q['usa_whatsapp'] == 'sim' else 'Há um WhatsApp no cadastro; o uso pela empresa ainda precisa ser confirmado.')
        pending.append('Validar volume e rotina de atendimento. O segmento não comprova demanda, demora ou perda de contatos.')
    elif agent:
        reasons.append('Informado na qualificação: ' + ', '.join(needs) + '.')
        if not agent_confirmed:
            pending.append('Confirmar o uso do WhatsApp; há um número no cadastro.')
    elif uses:
        pending.append('WhatsApp identificado: investigar perguntas repetitivas, agendamentos e perda de contatos antes de oferecer IA.')
    else:
        pending.append('Confirmar se atende pelo WhatsApp antes de avaliar um agente de IA.')
    if q['mensagens_dia'] is not None:
        reasons.append(f"Volume informado: {q['mensagens_dia']} mensagens por dia; volume isolado não confirma necessidade de IA.")
    offer = 'ambos' if site and agent else 'site' if site else 'whatsapp' if agent else 'investigar'
    confirmed = (not site or site_confirmed) and (not agent or agent_confirmed) and offer != 'investigar'
    return dict(oferta=offer, confianca='alta' if confirmed else 'baixa' if inferred else 'média' if offer != 'investigar' else 'baixa',
                situacao='Potencial estimado pelo segmento' if inferred else 'Necessidade confirmada na qualificação' if confirmed else 'Potencial para oferecer' if offer != 'investigar' else 'Informações insuficientes',
                motivos=reasons, confirmar=pending)


def validar_comercial(lead):
    """Validação também usada na restauração, antes de alterar a base."""
    organizacao({'tags': lead.get('tags', []), 'prioridade': lead.get('prioridade', 'normal')})
    qualificacao(lead.get('qualificacao', {}))
    for group in ('oportunidades', 'tarefas'):
        rows = lead.get(group, [])
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ValueError('Registros comerciais inválidos.')
        ids = set()
        for item in rows:
            if not isinstance(item, dict) or not re.fullmatch(r'[\w-]+', item.get('id', '')) or item['id'] in ids:
                raise ValueError('Registro comercial inválido ou repetido.')
            ids.add(item['id'])
            timestamp(item.get('criado_em'))
            if group == 'oportunidades':
                cents = item.get('valor_centavos')
                if type(cents) is not int or cents < 0:
                    raise ValueError('Valor monetário inválido no backup.')
                oportunidade(item | {'valor': str(Decimal(cents)/100)}, item)
                if item.get('fechado_em') is not None:
                    timestamp(item['fechado_em'])
            else:
                tarefa(item, item)
                if item.get('concluido_em') is not None:
                    timestamp(item['concluido_em'])


def validar_config(cfg):
    if 'etapas' in cfg:
        validar_etapas(cfg['etapas'])
    filters = cfg.get('filtros', [])
    if not isinstance(filters, list) or len(filters) > 50:
        raise ValueError('Filtros salvos inválidos.')
    seen = set()
    for row in filters:
        if not isinstance(row, dict) or not re.fullmatch(r'[\w-]+', row.get('id', '')) or row['id'] in seen:
            raise ValueError('Filtro salvo inválido.')
        seen.add(row['id']); texto(row.get('nome'), 80, True); validar_filtro(row.get('filtros'))


def relatorio(app, query):
    today = dt.date.today()
    start = dt.date.fromisoformat(query.get('inicio', [today.replace(day=1).isoformat()])[0])
    end = dt.date.fromisoformat(query.get('fim', [today.isoformat()])[0])
    if start > end or end.year > 2999 or (end-start).days > 3660:
        raise ValueError('Informe um período válido de até 10 anos.')
    begin = dt.datetime.combine(start, dt.time()).timestamp()
    finish = dt.datetime.combine(end+dt.timedelta(days=1), dt.time()).timestamp()
    def inside(value):
        return value is not None and begin <= value < finish
    def metrics(rows):
        events = [(l, e) for l in rows for e in l.get('historico', []) if inside(e['t'])]
        ops = [o for l in rows for o in l.get('oportunidades', [])]
        def reached(state):
            return len({l['id'] for l, e in events if e.get('status') == state or (not e.get('status') and e['tipo'] == 'status' and e['txt'] == 'Status: '+app.NOME_STATUS.get(state, ''))})
        return dict(leads=sum(inside(l['criado_em']) for l in rows),
                    contatos=sum(e['tipo'] in ('whatsapp', 'ligacao', 'email') for _, e in events),
                    respostas=reached('respondeu'), reunioes=reached('reuniao'),
                    oportunidades=sum(inside(o['criado_em']) for o in ops),
                    vendas=sum(o['estado']=='ganha' and inside(o.get('fechado_em')) for o in ops),
                    receita_centavos=sum(o['valor_centavos'] for o in ops if o['estado']=='ganha' and inside(o.get('fechado_em'))),
                    aberto_centavos=sum(o['valor_centavos'] for o in ops if o['estado']=='aberta'))
    groups = {}
    for lead in app.leads.values():
        source = (lead.get('buscas') or [lead.get('nicho') or 'Cadastro manual'])[0]
        groups.setdefault(source, []).append(lead)
    result = []
    for source, rows in groups.items():
        search = app.buscas.get(source)
        label = ', '.join(search['parametros']['nichos'])+' · '+search['parametros']['cidade'] if search else source
        result.append(dict(id=source, origem=label, **metrics(rows)))
    return {'inicio': start.isoformat(), 'fim': end.isoformat(), 'total': metrics(list(app.leads.values())), 'origens': sorted(result, key=lambda r: -r['receita_centavos'])}


def dispatch(h, app):
    """Retorna True quando a rota foi atendida, sob o mesmo lock da persistência."""
    path, method = h._rota(), h.command
    m = re.fullmatch(r'/api/leads/([\w-]+)/qualificacao', path)
    if m and method in ('GET', 'PATCH'):
        with app.lock:
            lead = app.leads.get(m[1])
            if lead is None:
                h._envia(404, {'erro': 'Lead não encontrado.'}); return True
            if method == 'PATCH':
                d = h._corpo()
                if not isinstance(d, dict):
                    raise ValueError('Qualificação inválida.')
                lead['qualificacao'] = qualificacao(lead.get('qualificacao', {}) | d)
                app.registrar(lead, 'qualificacao', 'Qualificação comercial atualizada')
                app.persistir(); h._envia(200, lead)
            else:
                h._envia(200, {'qualificacao': qualificacao(lead.get('qualificacao', {})), 'recomendacao': recomendar(lead)})
        return True
    if path == '/api/relatorios' and method == 'GET':
        with app.lock:
            h._envia(200, relatorio(app, urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)))
        return True
    if path == '/api/lixeira' and method == 'GET':
        with app.lock:
            h._envia(200, [dict(id=k, nome=v['lead']['nome'], excluido_em=v['excluido_em'], status=v['lead']['status'], oportunidades=len(v['lead'].get('oportunidades', [])), tarefas=len(v['lead'].get('tarefas', []))) for k, v in sorted(app.lixeira.items(), key=lambda x: -x[1]['excluido_em'])])
        return True
    m = re.fullmatch(r'/api/lixeira/([\w-]+)(/restaurar)?', path)
    if m and ((method == 'POST' and m[2]) or (method == 'DELETE' and not m[2])):
        with app.lock:
            if m[1] not in app.lixeira:
                h._envia(404, {'erro': 'Lead não encontrado na lixeira.'}); return True
            app.backup('antes-lixeira')
            if method == 'DELETE':
                del app.lixeira[m[1]]
                app.persistir(); h._envia(200, {'ok': True})
            else:
                if m[1] in app.leads:
                    h._envia(409, {'erro': 'O lead já existe na base.'}); return True
                lead = copy.deepcopy(app.lixeira[m[1]]['lead'])
                lead['buscas'] = [bid for bid in lead.get('buscas', []) if bid in app.buscas]
                if lead['status'] not in nomes_etapas(app):
                    lead['status'] = 'novo'
                for bid in lead['buscas']:
                    if lead['id'] not in app.buscas[bid].get('lead_ids', []):
                        app.buscas[bid].setdefault('lead_ids', []).append(lead['id'])
                app.registrar(lead, 'restaurado', 'Lead recuperado da lixeira; buscas já excluídas não são recriadas.')
                app.leads[lead['id']] = lead
                del app.lixeira[m[1]]; app.excluidos.pop(m[1], None)
                app.persistir(); h._envia(200, lead)
        return True
    if path == '/api/etapas' and method == 'PUT':
        d = h._corpo(); rows = validar_etapas(d.get('etapas'))
        with app.lock:
            ids = {r['id'] for r in rows}; migration = d.get('migrar', {})
            if not isinstance(migration, dict):
                raise ValueError('Migração inválida.')
            affected = [l for l in app.leads.values() if l['status'] not in ids]
            if any(migration.get(l['status']) not in ids for l in affected):
                raise ValueError('Escolha uma etapa de destino para os leads das etapas removidas.')
            app.backup('antes-etapas')
            for lead in affected:
                lead['status'] = migration[lead['status']]
                app.registrar(lead, 'status', 'Etapa migrada: ' + next(r['nome'] for r in rows if r['id'] == lead['status']))
            app.config['etapas'] = rows; app.persistir(); h._envia(200, app.config)
        return True
    if path == '/api/filtros' and method == 'POST':
        d = h._corpo()
        name, filters = texto(d.get('nome'), 80, True), validar_filtro(d.get('filtros'))
        with app.lock:
            rows = copy.deepcopy(app.config.get('filtros', []))
            if len(rows) >= 50:
                raise ValueError('Limite de 50 filtros salvos.')
            rows.append({'id': uuid.uuid4().hex, 'nome': name, 'filtros': filters})
            app.config['filtros'] = rows; app.persistir(); h._envia(200, rows)
        return True
    m = re.fullmatch(r'/api/filtros/([\w-]+)', path)
    if m and method == 'DELETE':
        with app.lock:
            app.config['filtros'] = [f for f in app.config.get('filtros', []) if f['id'] != m[1]]
            app.persistir(); h._envia(200, app.config['filtros'])
        return True
    m = re.fullmatch(r'/api/leads/([\w-]+)/organizacao', path)
    if m and method == 'PATCH':
        d = organizacao(h._corpo())
        with app.lock:
            if m[1] not in app.leads:
                h._envia(404, {'erro': 'Lead não encontrado.'}); return True
            lead = app.leads[m[1]]; lead.update(d)
            app.registrar(lead, 'organizacao', 'Tags e prioridade atualizadas')
            app.persistir(); h._envia(200, lead)
        return True
    if path == '/api/leads/manual' and method == 'POST':
        with app.lock:
            lead = contatos(app, h._corpo())
            if duplicado(lead, list(app.leads.values()) + [x['lead'] for x in app.lixeira.values()]):
                h._envia(409, {'erro': 'Lead semelhante já existe na base ou na lixeira.'}); return True
            app.registrar(lead, 'criado', 'Lead cadastrado manualmente')
            app.leads[lead['id']] = lead; app.persistir(); h._envia(201, lead)
        return True
    if path == '/api/leads/importar' and method == 'POST':
        with app.lock:
            d = h._corpo()
            try:
                result, valid = importar(app, d)
            except csv.Error as exc:
                raise ValueError('CSV malformado: ' + str(exc)) from exc
            if d.get('confirmar') is True:
                if result.get('precisa_mapear'):
                    raise ValueError('Mapeie a coluna Nome antes de importar.')
                app.backup('antes-importacao')
                for lead in valid:
                    app.registrar(lead, 'criado', 'Lead importado de CSV')
                    app.leads[lead['id']] = lead
                app.persistir()
                result['importados'] = len(valid)
            h._envia(200, result)
        return True
    m = re.fullmatch(r'/api/leads/([\w-]+)/contatos', path)
    if m and method == 'PATCH':
        with app.lock:
            if m[1] not in app.leads:
                h._envia(404, {'erro': 'Lead não encontrado.'}); return True
            lead = contatos(app, h._corpo(), app.leads[m[1]])
            app.registrar(lead, 'edicao', 'Dados de contato atualizados')
            app.leads[m[1]] = lead; app.persistir(); h._envia(200, lead)
        return True
    m = re.fullmatch(r'/api/leads/([\w-]+)/(oportunidades|tarefas)(?:/([\w-]+))?', path)
    if m and method in ('POST', 'PATCH', 'DELETE'):
        with app.lock:
            lid, group, item_id = m.groups()
            if lid not in app.leads:
                h._envia(404, {'erro': 'Lead não encontrado.'}); return True
            lead = app.leads[lid]
            items = copy.deepcopy(lead.get(group, []))
            old = next((x for x in items if x['id'] == item_id), None)
            if item_id and not old:
                h._envia(404, {'erro': 'Registro não encontrado.'}); return True
            if (method == 'POST' and item_id) or (method != 'POST' and not item_id):
                raise ValueError('Operação inválida.')
            if method == 'DELETE':
                items.remove(old)
                label = 'Registro removido'
            else:
                d = h._corpo()
                if old:
                    base = dict(old)
                    if group == 'oportunidades':
                        base['valor'] = str(Decimal(old['valor_centavos']) / 100)
                    d = base | d
                item = (oportunidade if group == 'oportunidades' else tarefa)(d, old)
                if old:
                    items[items.index(old)] = item
                else:
                    if len(items) >= 1000:
                        raise ValueError('Limite de 1.000 registros por lead.')
                    items.append(item)
                label = ('Oportunidade: ' + item['servico'] + ' — ' + item['estado']) if group == 'oportunidades' else ('Tarefa concluída: ' if item['concluida'] else 'Tarefa agendada: ') + item['titulo']
            lead[group] = items
            app.registrar(lead, 'comercial', label)
            app.persistir()
            h._envia(200, lead)
        return True
    return False
