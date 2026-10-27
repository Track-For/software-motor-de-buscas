"""Fluxos comerciais com banco e servidor isolados."""
import copy
import time
import unittest
import test_server as fixture
app = fixture.app


class Business(unittest.TestCase):
    setUp = fixture.CRM.setUp
    tearDown = fixture.CRM.tearDown
    req = fixture.CRM.req

    def test_offer_qualification_rules_and_persistence(self):
        path = '/api/leads/p1/qualificacao'
        app.leads['p1']['site'] = ''
        app.leads['p1']['whatsapp'] = '5541999999999'
        app.persistir()
        result = self.req(path)[1]['recomendacao']
        self.assertEqual(result['oferta'], 'site')
        self.assertEqual(result['confianca'], 'média')
        self.assertEqual(self.req(path, 'PATCH', {'mensagens_dia': True})[0], 400)
        self.assertEqual(self.req(path, 'PATCH', {'site': 'inventado'})[0], 400)
        self.assertEqual(self.req(path, 'PATCH', {'site': 'ausente', 'usa_whatsapp': 'sim', 'repetitivas': 'sim', 'mensagens_dia': 30})[0], 200)
        result = self.req(path)[1]['recomendacao']
        self.assertEqual((result['oferta'], result['confianca']), ('ambos', 'alta'))
        app.mesclar_leads(self.b, [app.lead_de(self.row)])
        app.persistir()
        self.assertEqual(app.store.read('leads')['p1']['qualificacao']['mensagens_dia'], 30)
        saved = app.snapshot()
        bad = copy.deepcopy(saved); bad['leads']['p1']['qualificacao']['mensagens_dia'] = -1
        self.assertEqual(self.req('/api/restaurar', 'POST', bad)[0], 400)
        self.req('/api/leads/p1', 'DELETE')
        self.req('/api/lixeira/p1/restaurar', 'POST', {})
        self.assertEqual(self.req(path)[1]['qualificacao']['mensagens_dia'], 30)
        self.assertEqual(self.req('/api/restaurar', 'POST', saved)[0], 200)
        self.req(path, 'PATCH', {'site': 'adequado'})
        self.assertEqual(self.req(path)[1]['recomendacao']['oferta'], 'whatsapp')
        self.req(path, 'PATCH', {'usa_whatsapp': 'nao'})
        self.assertEqual(self.req(path)[1]['recomendacao']['oferta'], 'investigar')

    def test_offer_social_domain_and_unknown_volume(self):
        lead = {'site': 'https://www.instagram.com/example', 'whatsapp': ''}
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'site')
        lead['site'] = 'https://instagram.com.example.org'
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'investigar')
        lead['qualificacao'] = {'mensagens_dia': 1000, 'usa_whatsapp': 'sim'}
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'investigar')

    def test_offer_segment_is_a_hypothesis_and_answers_override_it(self):
        lead = {'site': 'https://example.org', 'whatsapp': '5541999999999', 'categoria': 'Clínica odontológica'}
        result = app.business.recomendar(lead)
        self.assertEqual((result['oferta'], result['confianca']), ('whatsapp', 'baixa'))
        self.assertEqual(result['situacao'], 'Potencial estimado pelo segmento')
        lead['site'] = ''
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'ambos')
        lead['qualificacao'] = {'usa_whatsapp': 'nao'}
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'site')
        lead['qualificacao'] = {'repetitivas': 'nao', 'agendamentos': 'nao', 'perde_contatos': 'nao'}
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'site')
        lead['qualificacao'] = {'mensagens_dia': 0}
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'site')
        lead['qualificacao'] = {}
        lead['whatsapp'] = ''
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'site')
        lead['whatsapp'] = '5541999999999'
        lead['categoria'] = 'Categoria não reconhecida'
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'site')

    def test_opportunities_money_validation_update_and_merge(self):
        path = '/api/leads/p1/oportunidades'
        self.assertEqual(self.req(path, 'POST', {'servico': 'Site', 'valor': '100.001'})[0], 400)
        status, lead = self.req(path, 'POST', {'servico': 'Site', 'valor': '1234.56', 'previsao': '2027-01-15'})
        self.assertEqual(status, 200)
        item = lead['oportunidades'][0]
        self.assertEqual(item['valor_centavos'], 123456)
        self.req(path+'/'+item['id'], 'PATCH', {'estado': 'ganha'})
        app.mesclar_leads(self.b, [app.lead_de(self.row)])
        app.persistir()
        self.assertEqual(app.store.read('leads')['p1']['oportunidades'][0]['estado'], 'ganha')
        self.assertIsNotNone(app.leads['p1']['oportunidades'][0]['fechado_em'])

    def test_multiple_tasks_complete_reopen_and_edit(self):
        path = '/api/leads/p1/tarefas'
        for title in ('Ligar', 'Enviar proposta'):
            self.assertEqual(self.req(path, 'POST', {'titulo': title, 'prazo': time.time()+3600})[0], 200)
        item = app.leads['p1']['tarefas'][0]
        self.req(path+'/'+item['id'], 'PATCH', {'concluida': True})
        self.assertTrue(app.leads['p1']['tarefas'][0]['concluida'])
        self.req(path+'/'+item['id'], 'PATCH', {'concluida': False, 'titulo': 'Retornar'})
        self.assertEqual(app.leads['p1']['tarefas'][0]['titulo'], 'Retornar')
        self.assertIsNone(app.leads['p1']['tarefas'][0]['concluido_em'])
        self.assertEqual(len(app.store.read('leads')['p1']['tarefas']), 2)

    def test_manual_contact_and_csv_preview_duplicates(self):
        status, lead = self.req('/api/leads/manual', 'POST', {'nome': 'Empresa manual', 'email': 'a@example.org'})
        self.assertEqual(status, 201)
        self.assertEqual(self.req('/api/leads/manual', 'POST', {'nome': 'Empresa manual'})[0], 409)
        csv = 'Empresa;E-mail\nEmpresa manual;a@example.org\n"Nova; Empresa";nova@example.org\nInválida;errado\n'
        payload = {'csv': csv}
        result = self.req('/api/leads/importar', 'POST', payload)[1]
        self.assertEqual((result['validos'], result['duplicados'], result['erros']), (1, 1, 1))
        self.assertEqual(len(app.leads), 2)
        result = self.req('/api/leads/importar', 'POST', payload | {'confirmar': True})[1]
        self.assertEqual(result['importados'], 1)
        self.assertEqual(self.req('/api/leads/importar', 'POST', payload | {'confirmar': True})[1]['importados'], 0)
        self.assertEqual(self.req('/api/leads/p1/contatos', 'PATCH', {'nome': 'Nome corrigido', 'telefone': '(11) 3333-4444'})[0], 200)
        app.mesclar_leads(self.b, [app.lead_de(self.row)])
        self.assertEqual(app.leads['p1']['nome'], 'Nome corrigido')
        self.assertEqual(app.leads['p1']['tel_digitos'], '551133334444')

    def test_tags_filters_and_custom_stage_migration(self):
        self.assertEqual(self.req('/api/leads/p1/organizacao', 'PATCH', {'tags': ['Quente', 'Quente'], 'prioridade': 'alta'})[0], 200)
        self.assertEqual(app.leads['p1']['tags'], ['Quente'])
        result = self.req('/api/filtros', 'POST', {'nome': 'Quentes', 'filtros': {'tag': 'Quente', 'prioridade': 'alta'}})[1]
        self.assertEqual(len(result), 1)
        rows = self.req('/api/config')[1]['etapas']
        rows.insert(2, {'id': 'proposta', 'nome': 'Proposta enviada', 'cor': '#123456'})
        self.assertEqual(self.req('/api/etapas', 'PUT', {'etapas': rows})[0], 200)
        self.assertEqual(self.req('/api/leads/p1', 'PATCH', {'status': 'proposta'})[0], 200)
        self.assertEqual(app.leads['p1']['historico'][-1]['status'], 'proposta')
        reduced = [r for r in rows if r['id'] != 'proposta']
        self.assertEqual(self.req('/api/etapas', 'PUT', {'etapas': reduced})[0], 400)
        self.assertEqual(app.leads['p1']['status'], 'proposta')
        self.assertEqual(self.req('/api/etapas', 'PUT', {'etapas': reduced, 'migrar': {'proposta': 'contatado'}})[0], 200)
        self.assertEqual(app.store.read('leads')['p1']['status'], 'contatado')
        self.assertEqual(self.req('/api/leads/p1', 'PATCH', {'status': 'missing'})[0], 400)
        self.assertEqual(self.req('/api/filtros/'+result[0]['id'], 'DELETE')[1], [])

    def test_reports_period_source_and_money(self):
        self.req('/api/leads/p1/evento', 'POST', {'tipo': 'whatsapp'})
        self.req('/api/leads/p1', 'PATCH', {'status': 'respondeu'})
        self.req('/api/leads/p1/oportunidades', 'POST', {'servico': 'Site', 'valor': '100.50', 'estado': 'ganha'})
        self.req('/api/leads/p1/oportunidades', 'POST', {'servico': 'SEO', 'valor': '200', 'estado': 'aberta'})
        result = self.req('/api/relatorios')[1]
        self.assertEqual(result['total']['receita_centavos'], 10050)
        self.assertEqual(result['total']['aberto_centavos'], 20000)
        self.assertEqual(result['total']['respostas'], 1)
        self.assertEqual(result['origens'][0]['contatos'], 1)
        past = self.req('/api/relatorios?inicio=2020-01-01&fim=2020-01-31')[1]['total']
        self.assertEqual(past['receita_centavos'], 0)
        self.assertEqual(past['aberto_centavos'], 20000)
        self.assertEqual(self.req('/api/relatorios?inicio=2027-01-01&fim=2020-01-01')[0], 400)

    def test_trash_restore_keeps_business_and_shared_links(self):
        self.req('/api/leads/p1/oportunidades', 'POST', {'servico': 'Site', 'valor': '123'})
        self.req('/api/leads/p1/tarefas', 'POST', {'titulo': 'Ligar', 'prazo': time.time()+50})
        other = copy.deepcopy(self.b); other['id'] = 'b2'; app.buscas['b2'] = other
        app.leads['p1']['buscas'].append('b2'); app.persistir()
        self.req('/api/buscas/b1', 'DELETE')
        self.assertNotIn('p1', app.leads)
        self.assertEqual(self.req('/api/lixeira')[1][0]['oportunidades'], 1)
        self.assertIn('p1', app.store.read('lixeira'))
        status, lead = self.req('/api/lixeira/p1/restaurar', 'POST', {})
        self.assertEqual(status, 200)
        self.assertEqual(lead['buscas'], ['b2'])
        self.assertEqual(other['lead_ids'], ['p1'])
        self.assertEqual(lead['oportunidades'][0]['valor_centavos'], 12300)
        self.assertEqual(len(lead['tarefas']), 1)
        self.assertNotIn('p1', app.excluidos)
        self.assertEqual(app.store.read('lixeira'), {})
        self.req('/api/leads/p1', 'DELETE')
        self.req('/api/lixeira/p1', 'DELETE')
        self.assertNotIn('p1', app.lixeira)
        self.assertIn('p1', app.excluidos)

    def test_backup_restore_new_fields_and_legacy_compatibility(self):
        self.req('/api/leads/p1/tarefas', 'POST', {'titulo': 'Ligar', 'prazo': time.time()+50})
        saved = app.snapshot()
        self.req('/api/leads/p1', 'DELETE')
        with_trash = app.snapshot()
        self.assertEqual(self.req('/api/restaurar', 'POST', with_trash)[0], 200)
        self.assertIn('p1', app.lixeira)
        self.assertEqual(self.req('/api/restaurar', 'POST', saved)[0], 200)
        self.assertEqual(app.lixeira, {})
        bad = copy.deepcopy(saved); bad['leads']['p1']['tarefas'][0]['prazo'] = 'amanhã'
        self.assertEqual(self.req('/api/restaurar', 'POST', bad)[0], 400)
        self.assertIsInstance(app.leads['p1']['tarefas'][0]['prazo'], float)
        saved.pop('lixeira'); saved['leads']['p1'].pop('tarefas')
        self.assertEqual(self.req('/api/restaurar', 'POST', saved)[0], 200)


if __name__ == '__main__':
    unittest.main()
