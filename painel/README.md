# Prospecta — painel local

CRM em português para encontrar empresas, organizar contatos e acompanhar retornos.

## Abrir

- **Windows:** abra o Docker Desktop e execute `Iniciar.bat` na raiz.
- **macOS:** execute `Prospeccao.command`.
- **Terminal:** `docker compose up -d`, depois `python painel/server.py`.
- Acesse `http://localhost:8090`. Python 3.9+; nenhuma dependência Python adicional.
- Após atualizar o código, encerre o painel antigo com Ctrl+C e inicie novamente.

## Uso diário

O visual usa superfícies translúcidas inspiradas em liquid glass, transições com GSAP e um shader WebGL no destaque inicial. O GSAP 3.13.0 é servido localmente (`gsap.min.js`, licença no cabeçalho). Os efeitos respeitam a preferência por movimento reduzido, pausam o shader fora da tela ou com a aba oculta e mantêm uma alternativa CSS quando WebGL não está disponível. Os estilos ficam em `glass.css` e o ciclo de vida das animações em `effects.js`.

1. Em **Nova busca**, escolha nichos, cidade e tamanho da extração.
2. Em **Leads**, filtre os resultados ou abra uma ficha.
3. Abrir WhatsApp, telefone ou e-mail não registra envio. Após realizar o contato, use **Registrar contato realizado** e escolha o canal.
4. Na ficha, escolha **Próximo contato** e salve. A página **Próximos contatos** separa retornos pendentes dos futuros. Leads fechados ou descartados saem dessa agenda.
5. Use **Concluir retorno** após atender o lembrete, ou agende uma nova data. O motivo da perda pode ser registrado na mesma ficha.

## Gestão comercial

- Na ficha do lead, **Oferta recomendada** sugere site, agente de WhatsApp com IA, ambos ou qualificar antes de oferecer. Mostra motivos, confiança e pontos a confirmar. A ausência de site no cadastro ou um endereço de rede social indica potencial para site, sem afirmar que a empresa não tenha um.
- Preencha **Salvar qualificação** com a situação verificada do site, uso de WhatsApp, estimativa de mensagens diárias, perguntas repetitivas, agendamentos e perda de contatos. O agente é sugerido quando há sinal de uso do WhatsApp e uma dessas necessidades. Sem respostas, segmentos reconhecidos com WhatsApp podem receber uma indicação de potencial estimado, com confiança baixa e motivos explícitos; volume sozinho não determina a indicação. Respostas explícitas prevalecem sobre sinais do cadastro. “Necessidade confirmada” refere-se às respostas registradas por você, não a uma verificação externa.
- A recomendação usa regras locais, sem consultar conversas ou auditar sites automaticamente. A qualificação permanece em novas buscas, backups e restauração da lixeira. Leads antigos funcionam com respostas inicialmente desconhecidas.
- Na ficha do lead, cadastre oportunidades com serviço, valor, previsão e situação (aberta, ganha ou perdida), além de tarefas com prazo. Tarefas podem ser concluídas e reabertas em **Tarefas e retornos**.
- Use **Editar contato** para corrigir dados; tags, prioridade e filtros salvos ajudam a organizar a base.
- Em **Leads**, cadastre contatos manualmente ou importe CSV. Confira a prévia e o mapeamento antes de confirmar; linhas inválidas e duplicadas não são importadas. Limite: 5.000 linhas por arquivo.
- Em **Funil → Configurar etapas**, crie, renomeie e ordene etapas. Ao remover uma etapa com leads, escolha o destino deles.
- **Relatórios** reúne atividade e receita por período e origem, com exportação CSV. O valor em aberto representa a carteira atual, independentemente do período. Leads na lixeira não entram nos resultados.

## Excluir leads

- **Individual:** ficha → **Excluir este lead**.
- **Em lote:** selecione as caixas na tabela → **Excluir leads**.
- A seleção geral seleciona somente a página visível. As seleções permanecem ao mudar de página.
- Um diálogo confirma a quantidade e a ação. Cancelar o diálogo não altera dados.
- A exclusão move o lead para a **Lixeira** e remove seus vínculos ativos com as extrações. A restauração individual recupera histórico, tarefas, oportunidades e vínculos com buscas ainda existentes; buscas excluídas não são recriadas.
- **Excluir definitivamente** remove o registro da lixeira, mas mantém o bloqueio contra reaparecimento em buscas. Backups anteriores ainda podem recuperá-lo.
- IDs excluídos ficam numa lista local de exclusão para impedir reaparecimento em buscas atuais ou futuras. Restaurar um backup anterior recupera os leads e a lista de exclusão daquele momento.
- Antes da exclusão, o painel salva um backup completo em `painel/dados/backups/`.

Em **Buscas**, marque uma ou mais buscas e use **Excluir selecionadas**, ou abra uma busca e use **Excluir**. A exclusão apaga todos os leads encontrados nessas buscas, incluindo status, anotações e histórico, mesmo quando aparecem em outras buscas. Os vínculos dessas outras buscas também são removidos. Um backup é salvo antes da exclusão. Extrações em andamento precisam ser canceladas e encerradas antes de serem removidas.

## Dados e recuperação

O banco principal é `painel/dados/prospecta.sqlite3`, com transações SQLite e gravação apenas dos registros alterados. Na primeira abertura, os arquivos JSON antigos são importados sem serem apagados. Se um JSON estiver ilegível, a inicialização falha com uma mensagem e preserva o original; não cria uma base vazia por cima dele.

Em **Configurações → Backup e restauração**:

- **Baixar backup completo:** JSON com leads, histórico, agenda, mensagens, extrações e IDs excluídos.
- **Restaurar de arquivo:** selecione um backup exportado pelo painel.
- **Restaurar cópia:** escolha um backup automático salvo neste computador.

A restauração substitui a base, exige confirmação e cria uma cópia antes da mudança. Não pode ocorrer com buscas ativas. Buscas que estavam ativas no backup são restauradas como canceladas; não disparam extrações automaticamente.

Backups automáticos são criados ao iniciar e antes de exclusões/restaurações. Não há remoção automática de backups. Eles contêm os dados existentes no momento da cópia. Guarde uma cópia externa se precisar de proteção contra falha do computador. CSV é uma exportação de leads, não um backup completo.

Se o painel não iniciar por JSON corrompido, preserve a pasta `dados`, corrija/restaure o arquivo indicado e tente novamente. Se o próprio SQLite estiver corrompido, preserve a pasta, mova o banco e seus arquivos `-wal`/`-shm` para uma pasta de recuperação com o painel desligado e restaure um backup completo em uma base nova.

## Buscas e cancelamento

Em **Nova busca**, marque **Somente empresas sem site** para guardar apenas resultados sem endereço de site no Google Maps e sem site já conhecido pelo CRM. O filtro vale para resultados parciais, retomadas e repetição da busca. Empresas com link de rede social no campo de site também ficam de fora. O motor consulta os resultados normalmente e o painel aplica o filtro antes de incorporar os leads; por isso o total pode ser menor e não há garantia de que a empresa realmente não tenha site. Buscas antigas continuam com o comportamento anterior.

O painel salva o ID do job, as regiões concluídas e os resultados parciais. Em um reinício, reutiliza o job registrado e pula as regiões já concluídas. Resultados básicos são salvos antes do enriquecimento de contato.

O motor v1.18.1 [oferece exclusão de jobs, mas não cancelamento imediato de execução](https://github.com/gosom/google-maps-scraper/blob/v1.18.1/web/service.go). Ao cancelar, o painel espera a região ativa terminar, não agenda outras regiões e conserva os resultados anteriores. Durante enriquecimento, requisições de site já iniciadas podem terminar antes do cancelamento. Se a conexão com o motor cair com um job ativo, a fila aguarda a reconexão em vez de iniciar novas extrações em paralelo.

Há uma janela entre o motor aceitar um job e o painel persistir seu ID; uma interrupção exatamente nesse momento pode exigir conferir os jobs no motor. A API externa não oferece chave de idempotência.

## Limites e configuração

- O painel continua local, ligado a `127.0.0.1` e, quando disponível, `::1`.
- `PAINEL_PORT` muda a porta. `PAINEL_DATA_DIR` permite usar outra pasta de dados, útil para testes.
- O banco grava diferenças por registro; a API também oferece `/api/leads/pagina?offset=0&limit=100`, com limite máximo de 500 por resposta. A interface carrega essas páginas para manter filtros, exportação e funil existentes; ainda mantém a base em memória. Para bases muito grandes, a próxima evolução é filtragem e ordenação inteiramente no servidor.
- A fonte Outfit está incluída localmente, com licença em `fonts/OFL.txt`; o visual não depende do Google Fonts.
- Backups importados têm limite de 50 MB.

## Verificação

```powershell
python scripts/test_scrape.py
python painel/test_server.py
python painel/test_business.py
```

Os testes de CRM usam pastas temporárias e um servidor HTTP local; não acessam dados reais nem o Google.

Para testes visuais com Playwright e Edge:

```powershell
python painel/qa_server.py
# Em outro terminal, com playwright disponível:
node visual-qa.mjs
```

O servidor de QA usa dados fictícios isolados na porta 8091. `PLAYWRIGHT_MODULE` pode apontar para uma instalação existente do Playwright. Capturas ficam em `.qa/`, ignorada pelo Git.

Para validar os fluxos comerciais, inicie outro servidor isolado e execute o teste com Playwright e Edge disponíveis:

```powershell
$env:QA_PORT = '8092'
python painel/qa_server.py
# Em outro terminal:
node business-qa.cjs
```

O teste comercial cobre cadastro, oportunidades, tarefas, filtros salvos, importação CSV, etapas, relatórios e restauração da lixeira, além da largura da tela no celular. Reinicie o servidor de QA para começar com uma base fictícia limpa.
