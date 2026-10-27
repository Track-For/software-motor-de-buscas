"""Regressões do CRM em diretórios temporários, sem Docker ou dados reais."""
import copy
import json
import os
import tempfile
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

os.environ['PAINEL_DATA_DIR'] = tempfile.mkdtemp(prefix='prospecta-import-')
import server as app
from storage import read_json


class CRM(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.paths = patch.multiple(app, DADOS=self.temp.name,
            DIR_BUSCAS=os.path.join(self.temp.name, 'buscas'),
            ARQ_LEADS=os.path.join(self.temp.name, 'leads.json'),
            ARQ_CONFIG=os.path.join(self.temp.name, 'config.json'))
        self.paths.start()
        os.makedirs(app.DIR_BUSCAS)
        app.leads.clear(); app.buscas.clear(); app.config.clear(); app.fila.clear(); app.excluidos.clear()
        app.carregar()
        self.b = {'id': 'b1', 'parametros': {'nichos': ['Dentistas'], 'cidade': 'São Paulo', 'uf': 'SP', 'bairro': '', 'tamanho': 'rapida', 'redes': False},
                  'estado': 'concluida', 'criado_em': 1, 'lead_ids': [], 'jobs_motor': [], 'avisos': []}
        app.buscas['b1'] = self.b
        self.row = {'place_id': 'p1', 'title': 'Consultório Exemplo', 'phone': '(11) 99999-1234', 'address': 'São Paulo - SP'}
        self.b['lead_ids'] = app.mesclar_leads(self.b, [app.lead_de(self.row)])
        app.persistir()
        self.http = app.ThreadingHTTPServer(('127.0.0.1', 0), app.H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def tearDown(self):
        self.http.shutdown(); self.http.server_close()
        app.store.close(); app.store = None
        self.paths.stop(); self.temp.cleanup()

    def req(self, path, method='GET', data=None, raw=None):
        body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        r = urllib.request.Request(f'http://127.0.0.1:{self.http.server_port}'+path, data=body, method=method, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(r) as res:
                return res.status, json.load(res)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_search_without_website_filters_before_save_and_enrichment(self):
        self.b['parametros']['somente_sem_site'] = True
        self.b['geo'] = [-23.5, -46.6, None]
        app.leads['p1']['site'] = 'https://known.example.org'
        rows = [self.row, self.row | {'place_id': 'no-site'},
                self.row | {'place_id': 'with-site', 'website': 'https://example.org'},
                self.row | {'place_id': 'social', 'website': 'https://instagram.com/example'}]
        with patch.object(app, 'rodar_job', return_value=rows), patch.object(app, 'enriquecer') as enrich:
            app.executar(self.b)
            enrich.assert_not_called()
        self.assertEqual(self.b['lead_ids'], ['no-site'])
        self.assertEqual(self.b['novos'], 1)
        self.assertNotIn('with-site', app.leads)
        self.assertNotIn('social', app.leads)
        self.assertEqual(app.leads['p1']['site'], 'https://known.example.org')
        self.assertEqual(app.store.read('buscas')['b1']['parametros']['somente_sem_site'], True)
        self.b['parametros']['somente_sem_site'] = False
        self.assertIn('with-site', app.mesclar_leads(self.b, [app.lead_de(rows[2])]))

    def test_search_without_website_api_and_repeat(self):
        body = dict(nichos='Dentistas', cidade='São Paulo', uf='SP', tamanho='rapida', somente_sem_site=True)
        status, result = self.req('/api/buscas', 'POST', body)
        self.assertEqual(status, 201)
        self.assertTrue(result['parametros']['somente_sem_site'])
        bid = result['id']
        self.req('/api/buscas/'+bid+'/cancelar', 'POST', {})
        status, repeated = self.req('/api/buscas/'+bid+'/repetir', 'POST', {})
        self.assertEqual(status, 200)
        self.assertTrue(repeated['parametros']['somente_sem_site'])
        self.assertEqual(self.req('/api/buscas', 'POST', body | {'somente_sem_site': 'true'})[0], 400)

    def test_delete_individual_updates_all_searches_and_persists(self):
        self.assertEqual(self.req('/api/leads/p1','DELETE')[0],200)
        self.assertNotIn('p1',app.leads)
        self.assertEqual(self.b['lead_ids'],[])
        self.assertEqual(app.store.read('leads'),{})
        self.assertIn('p1',app.store.read('excluidos'))
        self.assertEqual(app.mesclar_leads(self.b,[app.lead_de(self.row)]),[])
        backups=os.listdir(os.path.join(app.DADOS,'backups'))
        saved=next(n for n in backups if 'antes-exclusao' in n)
        self.assertIn('p1',read_json(os.path.join(app.DADOS,'backups',saved),{})['leads'])

    def test_bulk_delete_idempotent_and_shared_leads(self):
        other=copy.deepcopy(self.b);other['id']='b2';app.buscas['b2']=other
        status,r=self.req('/api/leads/excluir','POST',{'ids':['p1','p1','missing']})
        self.assertEqual((status,r['excluidos']),(200,1))
        self.assertEqual(other['lead_ids'],[])
        self.assertEqual(self.req('/api/leads/excluir','POST',{'ids':['p1']})[1]['excluidos'],0)

    def test_contact_requires_explicit_event(self):
        self.req('/api/leads/p1')
        self.assertEqual(app.leads['p1']['status'],'novo')
        self.req('/api/leads/p1/evento','POST',{'tipo':'email'})
        self.assertEqual(app.leads['p1']['status'],'contatado')
        self.assertIsNotNone(app.leads['p1']['ultimo_contato'])

    def test_followup_and_history_survive_merge(self):
        self.req('/api/leads/p1','PATCH',{'retorno':2000000000,'motivo_perda':'Sem orçamento','status':'respondeu'})
        self.req('/api/leads/p1/evento','POST',{'tipo':'nota','txt':'Retornar segunda'})
        app.mesclar_leads(self.b,[app.lead_de(self.row)])
        app.persistir()
        l=app.store.read('leads')['p1']
        self.assertEqual(l['retorno'],2000000000)
        self.assertEqual(l['status'],'respondeu')
        self.assertEqual(l['historico'][-1]['txt'],'Retornar segunda')

    def test_full_backup_restore_and_reject_active_search(self):
        saved=app.snapshot()
        app.excluir_leads(['p1'])
        self.assertEqual(self.req('/api/restaurar','POST',saved)[0],200)
        self.assertIn('p1',app.leads)
        self.assertNotIn('p1',app.excluidos)
        app.buscas['b1']['estado']='rodando'
        self.assertEqual(self.req('/api/restaurar','POST',saved)[0],400)

    def test_malformed_restore_does_not_change_data(self):
        original=copy.deepcopy(app.leads)
        bad=app.snapshot();bad['leads']['p1'].pop('historico')
        self.assertEqual(self.req('/api/restaurar','POST',bad)[0],400)
        self.assertEqual(app.leads,original)
        self.assertEqual(self.req('/api/leads/excluir','POST',raw=b'{broken')[0],400)
        self.assertEqual(self.req('/api/leads/excluir','POST',{'ids':'p1'})[0],400)

    def test_corrupt_legacy_file_is_preserved(self):
        path=os.path.join(app.DADOS,'broken.json')
        with open(path,'w') as f:f.write('{bad')
        with self.assertRaises(RuntimeError):read_json(path,{})
        with open(path) as f:self.assertEqual(f.read(),'{bad')

    def test_failed_write_restores_memory_and_database(self):
        original=copy.deepcopy(app.leads['p1'])
        with patch.object(app.store,'sync',side_effect=sqlite3.OperationalError('disk full')):
            status,_=self.req('/api/leads/p1','PATCH',{'status':'fechado'})
        self.assertEqual(status,500)
        self.assertEqual(app.leads['p1'],original)
        self.assertEqual(app.store.read('leads')['p1'],original)

    def test_legacy_migration_is_atomic_when_a_file_is_corrupt(self):
        app.store.close()
        # Use outro diretório, sem tocar o banco da fixture.
        with tempfile.TemporaryDirectory() as directory:
            os.mkdir(os.path.join(directory,'buscas'))
            original=json.dumps(app.leads)
            with open(os.path.join(directory,'leads.json'),'w') as f:f.write(original)
            with open(os.path.join(directory,'buscas','bad.json'),'w') as f:f.write('{broken')
            with patch.multiple(app,DADOS=directory,DIR_BUSCAS=os.path.join(directory,'buscas'),ARQ_LEADS=os.path.join(directory,'leads.json'),ARQ_CONFIG=os.path.join(directory,'config.json')):
                app.leads.clear();app.buscas.clear();app.config.clear()
                with self.assertRaises(RuntimeError):app.carregar()
                self.assertEqual(app.store.read('config'),{})
                with open(os.path.join(directory,'leads.json')) as f:self.assertEqual(f.read(),original)
                app.store.close()
        app.leads.clear();app.buscas.clear();app.config.clear();app.carregar()

    def test_sqlite_restart_keeps_deleted_leads_deleted(self):
        app.excluir_leads(['p1'])
        app.store.close();app.leads.clear();app.buscas.clear();app.config.clear();app.excluidos.clear()
        app.carregar()
        self.assertEqual(app.leads,{})
        self.assertIn('p1',app.excluidos)

    def test_page_limits(self):
        status,p=self.req('/api/leads/pagina?limit=1')
        self.assertEqual(status,200);self.assertEqual(p['total'],1);self.assertEqual(len(p['items']),1)
        self.assertNotIn('historico',p['items'][0])
        self.assertEqual(self.req('/api/leads/pagina?offset=1')[1]['items'],[])

    def test_delete_search_removes_worked_shared_leads_and_persists(self):
        other = copy.deepcopy(self.b)
        other.update(id='b2', linhas_parciais=[self.row], enriquecidos={'p1': {}})
        app.buscas['b2'] = other
        app.leads['p1'].update(status='fechado', obs='Cliente', buscas=['b1', 'b2'])
        other['lead_ids'] += app.mesclar_leads(other, [app.lead_de(dict(self.row, place_id='p2'))])
        app.persistir()
        status, result = self.req('/api/buscas/b1', 'DELETE')
        self.assertEqual((status, result['excluidos']), (200, 1))
        self.assertNotIn('b1', app.store.read('buscas'))
        self.assertEqual(set(app.store.read('leads')), {'p2'})
        self.assertEqual(other['lead_ids'], ['p2'])
        self.assertEqual(other['linhas_parciais'], [])
        self.assertEqual(other['enriquecidos'], {})
        self.assertIn('p1', app.store.read('excluidos'))
        self.assertEqual(app.mesclar_leads(other, [app.lead_de(self.row)]), [])
        saved = next(n for n in os.listdir(os.path.join(app.DADOS, 'backups')) if 'antes-exclusao-busca' in n)
        original = read_json(os.path.join(app.DADOS, 'backups', saved), {})
        self.assertIn('b1', original['buscas'])
        self.assertEqual(original['leads']['p1']['obs'], 'Cliente')

    def test_delete_search_failed_write_restores_search_and_leads(self):
        with patch.object(app.store, 'sync', side_effect=sqlite3.OperationalError('disk full')):
            self.assertEqual(self.req('/api/buscas/b1', 'DELETE')[0], 500)
        self.assertIn('b1', app.buscas)
        self.assertIn('p1', app.leads)
        self.assertNotIn('p1', app.excluidos)

    def test_running_search_cannot_be_deleted(self):
        self.b['estado']='rodando'
        self.assertEqual(self.req('/api/buscas/b1','DELETE')[0],409)
        self.assertIn('b1',app.buscas)

    def test_cancel_queued_search(self):
        self.b['estado']='na_fila';app.fila.append('b1')
        self.assertEqual(self.req('/api/buscas/b1/cancelar','POST',{})[0],200)
        self.assertEqual(app.fila,[]);self.assertEqual(self.b['estado'],'cancelada')

    def test_resume_active_job_does_not_create_another(self):
        self.b.update(job_atual='engine1',job_inicio=app.time.time())
        responses=[(200,b'{"Status":"ok"}'),(200,b'place_id,title\np2,Empresa B\n')]
        with patch.object(app.kit,'req',side_effect=responses) as req:
            rows=app.rodar_job(self.b,{'max_time':600},'Região 1')
        self.assertEqual(rows[0]['place_id'],'p2')
        self.assertTrue(all(c.args[0]=='GET' for c in req.call_args_list))

    def test_cancel_waits_for_engine_terminal_state(self):
        self.b.update(job_atual='engine1',job_inicio=app.time.time(),cancelar=True)
        with patch.object(app.kit,'req',side_effect=[(200,b'{"Status":"working"}'),(200,b'{"Status":"ok"}')]) as req, patch.object(app.time,'sleep'):
            with self.assertRaises(app.Cancelada):app.rodar_job(self.b,{'max_time':600},'Região 1')
        self.assertEqual(req.call_count,2);self.assertNotIn('job_atual',self.b)

    def test_resume_completed_region_uses_saved_rows(self):
        self.b.update(geo=['-23.5','-46.6',None],regioes_concluidas=[1],linhas_parciais=[self.row])
        with patch.object(app,'rodar_job') as run,patch.object(app,'localizar') as geo:
            app.executar(self.b)
        run.assert_not_called();geo.assert_not_called()
        self.assertEqual(self.b['estado'],'concluida');self.assertEqual(self.b['lead_ids'],['p1'])


if __name__=='__main__':
    unittest.main(verbosity=2)
