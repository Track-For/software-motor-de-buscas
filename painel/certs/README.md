# Certificados para diagnóstico HTTPS

`cacert.pem` é a cópia sem alterações do conjunto de autoridades públicas Mozilla distribuído pelo pacote Certifi 2026.10.19, disponível no ambiente de desenvolvimento. A licença MPL 2.0 está em `LICENSE`.

O diagnóstico adiciona essas autoridades às autoridades padrão do sistema. A verificação do certificado e do nome do servidor permanece obrigatória. Nenhuma opção para ignorar TLS foi adicionada.

Ao atualizar o Certifi, substitua o arquivo completo por sua versão oficial, preserve a licença e atualize a versão registrada aqui. Não adicione certificados de sites individuais como autoridades confiáveis.
