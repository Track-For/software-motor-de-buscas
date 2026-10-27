"""Servidor de QA com dados fictícios e isolados. Nunca acessa o motor real."""
import os
import tempfile
import time

os.environ['PAINEL_DATA_DIR'] = tempfile.mkdtemp(prefix='prospecta-qa-')
os.environ['PAINEL_PORT'] = '8091'
import server as app

app.carregar()
b = {'id':'demo','parametros':{'nichos':['Arquitetura'],'cidade':'Curitiba','uf':'PR','bairro':'','tamanho':'padrao','redes':True},
     'estado':'concluida','etapa':'Concluída','criado_em':time.time()-86400,'concluido_em':time.time(), 'lead_ids':[], 'avisos':[], 'jobs_motor':[]}
app.buscas['demo']=b
names=['Ateliê Aurora Arquitetura','Estúdio Alameda','Casa Norte Interiores','Forma Arquitetura','Linha Clara Projetos','Pátio Design','Oliva Arquitetos','Terracota Estúdio']
rows=[{'place_id':f'demo{i}','title':name,'category':'Escritório de arquitetura','phone':f'(41) 99999-100{i}',
       'address':'Curitiba - PR','complete_address':'{"city":"Curitiba","borough":"Batel","state":"PR"}',
       'website':'https://example.org' if i%3 else '', 'review_rating':str(4.5+i/20),'review_count':str(19+i*13),'emails':'contato@example.org' if i%2 else ''} for i,name in enumerate(names)]
b['lead_ids']=app.mesclar_leads(b,[app.lead_de(r) for r in rows])
for i,l in enumerate(app.leads.values()):
    l['status']=app.STATUS_LEAD[i%6]
    l['retorno']=time.time()+((i-2)*7200)
    if i%2: app.registrar(l,'whatsapp','')
app.persistir()
app.motor_ok=lambda:True
print('QA isolado: http://127.0.0.1:8091',flush=True)
app.ThreadingHTTPServer(('127.0.0.1',8091),app.H).serve_forever()
