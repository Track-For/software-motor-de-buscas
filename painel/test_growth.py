"""Aquisição: APIs isoladas, rede simulada e validação dos resultados."""
import copy
import socket
import time
import unittest
from unittest.mock import patch
import test_server as fixture
import growth
import site_audit

app = fixture.app


class Growth(unittest.TestCase):
    setUp = fixture.CRM.setUp
    tearDown = fixture.CRM.tearDown
    req = fixture.CRM.req

    def action(self, suffix, data=None, method='POST'):
        return self.req('/api/leads/p1/'+suffix, method, data or {})

    def approach(self):
        status, lead = self.action('abordagens', {'oferta': 'site', 'estilo': 'consultiva', 'texto': 'Mensagem revisada'})
        self.assertEqual(status, 200)
        return lead['abordagens'][-1]['id']

    def test_ranking_explains_and_excludes_closed_and_optout(self):
        lead = app.leads['p1']
        now = time.time()
        before = growth.ranking(lead, now)
        self.assertEqual(before['pontos'], sum(x['pontos'] for x in before['motivos']))
        lead['ultimo_contato'] = now
        self.assertLess(growth.ranking(lead, now)['pontos'], before['pontos'])
        lead['status'] = 'fechado'
        self.assertEqual(self.req('/api/prioridades')[1], [])
        lead['status'] = 'novo'
        self.action('preferencia-contato', {'nao_contatar': True})
        self.assertEqual(self.req('/api/prioridades')[1], [])
        self.assertEqual(self.action('abordagens', {'oferta': 'site', 'previa': True})[0], 400)
        self.assertEqual(self.action('evento', {'tipo': 'whatsapp'})[0], 400)

    def test_draft_is_not_a_contact_and_can_be_revised(self):
        status, preview = self.action('abordagens', {'oferta': 'site', 'estilo': 'direta', 'previa': True})
        self.assertEqual(status, 200)
        self.assertIn(app.leads['p1']['nome'], preview['texto'])
        self.assertNotIn('não tem site', preview['texto'])
        self.assertNotIn('abordagens', app.leads['p1'])
        aid = self.approach()
        self.assertIsNone(app.leads['p1']['ultimo_contato'])
        self.assertEqual(self.action('contato-comercial', {'canal': 'whatsapp', 'abordagem_id': aid})[0], 200)
        event = next(e for e in app.leads['p1']['historico'] if e['tipo'] == 'whatsapp')
        self.assertEqual((event['oferta'], event['abordagem']), ('site', 'consultiva'))

    def test_sequence_waits_for_contact_preserves_task_metadata_and_stops(self):
        self.action('sequencia', {'acao': 'iniciar'})
        self.assertEqual(app.leads['p1']['sequencia']['estado'], 'aguardando_contato')
        self.action('evento', {'tipo': 'email'})
        lead = app.leads['p1']
        self.assertEqual(len(lead['tarefas']), 3)
        task = lead['tarefas'][0]
        self.assertAlmostEqual(task['prazo']-lead['ultimo_contato'], 3*86400)
        self.action('tarefas/'+task['id'], {'concluida': True}, 'PATCH')
        self.assertEqual(lead['tarefas'][0]['sequencia_id'], lead['sequencia']['id'])
        self.action('resposta')
        self.assertEqual(lead['sequencia']['estado'], 'interrompida')
        self.assertTrue(all(t['concluida'] or t.get('cancelada') for t in lead['tarefas']))
        self.assertEqual(self.action('tarefas/'+lead['tarefas'][1]['id'], {'concluida': False}, 'PATCH')[0], 400)

    def test_sequence_stops_on_bulk_status_and_optout(self):
        self.action('sequencia', {'acao': 'iniciar'})
        self.action('evento', {'tipo': 'email'})
        self.req('/api/leads/lote', 'POST', {'ids': ['p1'], 'status': 'fechado'})
        self.assertEqual(app.leads['p1']['sequencia']['estado'], 'interrompida')

    def test_conversion_cohort_counts_distinct_leads(self):
        aid = self.approach()
        for _ in range(2):
            self.action('contato-comercial', {'canal': 'email', 'abordagem_id': aid})
        for _ in range(2):
            self.action('resposta')
        self.action('oportunidades', {'servico': 'Site', 'valor': '100.50', 'estado': 'ganha'})
        data = self.req('/api/conversoes?agrupar=oferta')[1]['grupos'][0]
        self.assertEqual((data['contatados'], data['respostas'], data['clientes']), (1, 1, 1))
        self.assertEqual(data['taxa_clientes'], 100)
        self.assertEqual(data['receita_centavos'], 10050)
        self.assertEqual(self.req('/api/conversoes?inicio=2020-01-01&fim=2020-01-31')[1]['grupos'], [])
        self.assertEqual(self.req('/api/conversoes?agrupar=bad')[0], 400)

    def test_proposal_edit_send_accept_idempotent_and_backup(self):
        data = dict(servico='Site', escopo='Cinco páginas', prazo='20 dias', valor='1234.56', condicoes='50% na aprovação')
        status, lead = self.action('propostas', data)
        self.assertEqual(status, 200)
        pid = lead['propostas'][0]['id']
        self.action('propostas/'+pid, {'prazo': '30 dias'}, 'PATCH')
        self.action('propostas/'+pid, {'estado': 'enviada'}, 'PATCH')
        self.action('propostas/'+pid, {'estado': 'enviada'}, 'PATCH')
        self.assertEqual(len(app.leads['p1']['tarefas']), 1)
        self.assertEqual(self.action('propostas/'+pid, {'prazo': '10 dias'}, 'PATCH')[0], 400)
        self.action('propostas/'+pid, {'estado': 'aceita'}, 'PATCH')
        self.action('propostas/'+pid, {'estado': 'aceita'}, 'PATCH')
        lead = app.leads['p1']
        self.assertEqual(len(lead['oportunidades']), 1)
        self.assertEqual(lead['oportunidades'][0]['valor_centavos'], 123456)
        self.assertEqual(lead['status'], 'fechado')
        self.assertTrue(lead['tarefas'][0]['concluida'])
        saved = app.snapshot()
        bad = copy.deepcopy(saved); bad['leads']['p1']['propostas'][0]['valor_centavos'] = -1
        self.assertEqual(self.req('/api/restaurar', 'POST', bad)[0], 400)
        self.req('/api/leads/p1', 'DELETE')
        self.req('/api/lixeira/p1/restaurar', 'POST', {})
        self.assertEqual(app.leads['p1']['propostas'][0]['estado'], 'aceita')
        self.assertEqual(self.req('/api/restaurar', 'POST', saved)[0], 200)

    def test_audit_api_persistence_and_evidence(self):
        app.leads['p1']['site'] = 'https://example.org'
        html = '<meta name="viewport" content="width=device-width"><form></form><a href="https://wa.me/5511999999999">Contato</a><p>Serviços</p><a href="/missing">Página</a>'
        with patch.object(site_audit, 'fetch', side_effect=[(200,'https://example.org','text/html',html),(404,'https://example.org/missing','text/html','')]):
            status, lead = self.action('diagnostico')
        self.assertEqual(status, 200)
        self.assertTrue(all(x['encontrado'] for x in lead['diagnostico']['verificacoes']))
        self.assertEqual(lead['diagnostico']['links'][0]['estado'], 'quebrado')
        self.assertIn('HTTP 404', growth.draft(lead, 'site', 'direta'))
        self.assertEqual(app.business.recomendar(lead)['oferta'], 'site')
        self.assertEqual(app.store.read('leads')['p1']['diagnostico']['estado'], 'concluido')
        self.assertEqual(self.req('/api/restaurar','POST',app.snapshot())[0], 200)


class SiteAudit(unittest.TestCase):
    def test_private_addresses_and_credentials_rejected(self):
        for ip in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1'):
            with patch.object(socket, 'getaddrinfo', return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,80))]):
                with self.assertRaises(ValueError):
                    site_audit.public_target('http://example.org')
        with self.assertRaises(ValueError):
            site_audit.public_target('http://user:password@example.org')

    def test_dynamic_html_is_not_reported_as_confirmed_defect(self):
        with patch.object(site_audit, 'fetch', return_value=(200,'https://example.org','text/html','<script>services form</script>')):
            report = site_audit.analyze('https://example.org')
        self.assertFalse(any(c['encontrado'] for c in report['verificacoes']))
        self.assertIn('JavaScript', report['resumo'])
        with patch.object(site_audit, 'fetch', return_value=(403,'https://example.org','text/html','')):
            self.assertEqual(site_audit.analyze('https://example.org')['estado'], 'inconclusivo')


if __name__ == '__main__':
    unittest.main()
