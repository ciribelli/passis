## Passis - Meu Assistente Pessoal
##### Aluno: Otávio Ciribelli Borges (https://github.com/ciribelli) 
##### Orientador: Anderson Nascimento (https://github.com/insightds)

Trabalho apresentado ao curso [BI MASTER](https://ica.puc-rio.ai/bi-master) como pré-requisito para conclusão de curso e obtenção de crédito na disciplina "Projetos de Sistemas Inteligentes de Apoio à Decisão". - [Link para o código](https://github.com/link_do_repositorio). - [Link para a monografia](https://link_da_monografia.com). - Trabalhos relacionados: - [Nome do Trabalho 1](https://link_do_trabalho.com). - [Nome do Trabalho 2](https://link_do_trabalho.com).
### Resumo
Este trabalho visa apresentar uma abordagem inovadora para apropriação e uso dos dados gerados diariamente por cada indivíduo em múltiplos propósitos e contextos. Em contraste com o paradigma que grandes corporações comumente oferecem enquanto experiência para seus usuários, a proposta desta solução de Assistente Pessoal (Passis) se diferencia pelo gerenciamento das informações pessoais de forma segura e em formato aberto e flexível quanto à forma de consumo e utilização desses dados. Neste contexto, o Passis objetiva a promoção de uma rotina de maior produtividade para seus usuários por meio do aumento do conhecimento de suas próprias informações que são geradas e armazenadas pelo sistema. Com uma inovadora forma de combinação dos dados pessoais registrados com as informações do meio onde o indivíduo está inserido, a solução habilita que decisões sejam tomadas em tempo real com menor grau de subjetividade. O Assistente foi desenvolvido em um conjunto de implementações modeladas em formato de microsserviços com uma Interface Programável de Aplicação (API) que comunica com rotinas automatizadas e comandos do usuário que acontecem preferencialmente em linguagem natural pelo aplicativo de mensagem Whatsapp. Sendo seu código-fonte desenvolvido em formato aberto (*open source*), pode ser implementado em diferentes plataformas e conectado com os principais serviços de visualização de dados e plataformas de *Business Inteligence* disponíveis no mercado. 
### Abstract

This work aims to present an innovative approach for the appropriation and use of data generated daily by each individual for multiple purposes and contexts. In contrast to the paradigm commonly offered by large corporations as a user experience, the proposed solution of a Personal Assistant (Passis) stands out for securely managing personal information in an open and flexible format regarding how the data is consumed and applied. In this context, Passis aims to promote a more productive routine for its users by increasing their awareness of their own information, which is generated and stored by the system. With an innovative way of combining recorded personal data with information from the environment in which the individual is embedded, the solution enables real-time decision-making with a lower degree of subjectivity. The Assistant was developed using a set of implementations modeled as microservices with an Application Programming Interface (API) that communicates with automated routines and user commands, preferably in natural language through the messaging app WhatsApp. As its source code is developed in an open-source format, it can be implemented on different platforms and connected to major data visualization services and Business Intelligence platforms available on the market.
### 1. Introdução
#### 1.1 Contextualização
Uma discussão importante que se intensificou na última década é a questão da soberania e uso dos dados pessoais. Não é incomum vermos ações judiciais entre grandes corporações globais e países que buscam esclarecimento sobre a propriedade e o uso não-consentido de dados de cidadãos e instituições, sejam governamentais ou não. No campo individual, pessoas se submetem à uma realidade aparentemente imutável onde o acesso à recursos e lugares se dá apenas e exclusivamente sob a condição de sessão de seus dados pessoais. Ao consentir diariamente com novas políticas de termos e condições, empresas privadas e autoridades públicas fazem uso de dados pessoais em uma escala sem precedentes para realizar suas atividades[^3].

Para além da segurança dos dados, que certamente é o tópico de maior importância no contexto da discussão, existe uma segunda temática ligada ao uso efetivo das informações que são geradas diariamente por indivíduos. Diferentes fontes que podem ser encontradas na internet versam sobre o volume de dados que são gerados diariamente por pessoas. Um desses estudos, publicado pela empresa Edge Delta* que é especializada em estudos de tendência sobre geração de dados, afirma que o volume médio diário de dados produzidos por uma pessoa usuária de internet[^4] é da ordem de 146.880 MB.  

Paralelamente à corrida pelo "novo ouro" que são os dados privados de indivíduos e corporações, no final de novembro de 2022 ganhou notória publicidade uma aplicação conversacional que utiliza o modelo denominado GPT-3 lançado em dezembro daquele ano pela empresa OpenAI. Baseado na também popular publicação "Atention is all you need" (Vaswani, A. et al)[^?] que propôs em o modelo de Transforms, tal lançamento surpreendeu o mercado de tecnologia com uma capacidade até então desconhecida de agregação e manipulação de dados, trazendo um novo paradigma para uma efetiva aplicação das informações geradas digitalmente. 

A mudança de paradigma é tamanha que, de acordo com o documento *Strategic Planning Assumptions*[^5], a autores da instituição Gartner preveem que 90% da força de trabalho das empresas será assistida por Inteligência Artificial generativa até o 2025. A versatilidade única dos modelos de linguagem natural da geração pós-_transforms_ revelou uma disparada no aparecimento de soluções do tipo assistentes pessoais. A figura 1 revela uma prova material do crescente interesse por soluções do tipo assistentes pessoais que são implementados por meio de Inteligência Artificial.

![image](https://github.com/user-attachments/assets/fce8d20a-ca7d-46b5-8303-8c620237799a)


_Figura 01 - Aumento do interesse por soluções do tipo “AI Personal Assistant”, segundo informações do site Google Trends_

#### 1.2 Motivação
Suponhamos que alguém decida fazer uma promessa de ano novo comprometendo-se a dormir mais cedo no ano que se inicia, na busca por uma vida mais equilibrada e saudável. Ou ainda, uma pessoa se comprometa em fazer caminhadas diárias para melhorar seu desempenho cardiorespiratório. Ou por último, alguém busque por uma sugestão de programação para uma tarde de sábado de acordo com suas preferências e as condições climáticas daquele dia. Naturalmente, cada uma dessas pessoas poderia buscar um aplicativo de caminhadas, baixar um monitor de sono para seu _smartwatch_ ou fazer uma busca numa rede social ou portal de eventos para saber a programação de jogos naquela tarde. Acontece que todas essas são informações estão persistidas de forma estanque em suas origens, com pouca ou nenhuma personalização de conteúdo para atender a real necessidade desses indivíduos. O aplicativo de caminhadas irá calcular o ritmo de caminhada, apresentar o tempo e a velocidade média num _dashboard_. Um mapa também será exibido para que as pessoas interajam com sua caminhada. Em verdade, o que se desejava com o aplicativo era apenas saber se as caminhadas estão sendo mais frequentes neste ano quando comparadas ao ano anterior. Tal raciocínio vale para o aplicativo de sono e o site de busca por entretenimento. Eventualmente, num dia chuvoso e com um clássico de futebol exibido na TV aberta envolvendo seu time do coração, poderia ser essa a sugestão que mais agrada quem procura o que fazer com seu tempo.

Muito provalvemente, a pergunta que se quer responder neste trabalho, em meio à vastidão de informações geradas diariamente por pessoas e sistemas, é: *qual o melhor recorte de dados que deve ser consultado para prover a resposta mais adequada para uma determinada necessidade*?

#### 1.3 Proposição

A proposta deste trabalho, neste contexto de altíssima disponibilidade de dados e recursos tecnológicos que permitem imensa agregação de informações de diferentes origens em modelos de liguagem de grande escala, consiste em propor um *assistente pessoal que forneça sugestões 
em assuntos de domínio das memórias particulares, localização geográfica, compromissos (checkins), clima, trânsito e eventos externos*[^7]. 

Para o assistente Passis, contrariando a estatística da montanha de dados que se estima que seja gerada por pessoas diariamentes, destinou-se apenas 11kB por dia, em média, para a geração de sua base de dados.

************************************************ estamos agora na hora de falar da UX ************************
O uso 
Insights:
-Assistente pessoal em código aberto que se propõe a entender a rotina pessoal ou profissional do usuário e sugerir aperfeiçoamentos com base na observação e/ou métricas propostas pelo usuário
-Investir em UX “transparente” ao usuário
-Permitir classificação de dados

Strategic Planning Assumptions
By 2025, generative AI will be a workforce partner for 90% of companies globally.

Organizations in this future are trying to maximize the impact of their employees,by focusing on taking tasks that are rote, repetitive, or rapidly produce feedback and moving them to machines and technology. This reduces their rate of attrition and allows them to get more out of their existing employees.





- motivação ligada à crescente demanda por assistentes pessoais, principalmente após o advento da genAI
- gráfico do google
- referencia do gartner
- soberania dos dados pessoais
- tentar lembrar do termo do professor



### 2. Modelagem




A arquitetura do sistema é composta por um backend desenvolvido em Python por meio de um servidor web que implementa o _framework_ Flask que gerencia as rotas e endpoints, um conjunto de funções de processamento e busca, e um modelo de linguagem de larga escala (LLM) que gera as respostas contextuais. Esses elementos estão apresentados. Além do servidor principal, um banco de dados Postgres também suporta o funcionamento da aplicação guardando as informações do usuário relativamente a memórias, documentos, compromissos ("checkins") etc. A figura XXXX apresenta um panorama da visão funcional do sistema.

![image](https://github.com/user-attachments/assets/f899012d-10e1-45f9-8437-236883fa67d7)

#### app.py
- Este arquivo é a entrada principal do aplicativo Flask. Nele estão contidas as rotas e endpoints da API. Nele também está implementado um trecho importante do sistema que é uma estrutura tipicamente reconhecida como _webhook_. Este trecho do código funciona como um ponto de espera e conexão ativa com a API da Meta e seu aplicativo Whatsapp Business. Portanto, ainda que o conceito de arquitetura contemple a propriedade de agnosticidade à interface por usar exclusivamente as rotas e endpoints do arquivo app.py para seu funcionamento, neste webhook é onde acontece a implementação desta prova de conceito que foi feita utilizando o Whatsapp enquanto interface de usuário.
- Uma lista completa das rotas e endpoints do arquivo app.py estão listadas na tabela a seguir:

| Rota                          | Métodos           | Descrição                                                       |
|-------------------------------|-------------------|-----------------------------------------------------------------|
| /                             | GET               | Página inicial do servidor                                       |
| /v1/jogos/<data_hora>         | GET               | Obtém jogos para uma data/hora específica (Central de jogos UOL) |
| /v1/time/<nome_time>          | GET               | Obtém informações sobre um time específico (Central de jogos UOL) |
| /v1/x/                        | GET               | Busca informações de um perfil no X (antigo Twitter)           |
| /v1/clima                     | GET               | Obtém informações climáticas (API Clima Tempo)                 |
| /webhook                      | POST, GET         | Webhook para interações (POST) e verificações (GET) com a Meta |
| /checkin                      | POST, GET         | Cria (POST) ou lista (GET) check-ins                           |
| /checkin/<checkin_id>         | GET, PUT, DELETE  | Obtém, atualiza ou deleta um check-in específico                |
| /adicionar_clima              | POST              | Adiciona dados climáticos                                       |
| /deletar_clima/<clima_id>     | DELETE            | Deleta um registro climático específico                          |
| /criar_documento              | POST              | Cria um novo documento binário                                   |
| /recuperar_documento/<documento_id> | GET         | Recupera um documento binário específico                        |
| /recuperar_lista_documentos   | GET               | Lista todos os documentos binários                               |
| /excluir_documento/<documento_id> | DELETE        | Exclui um documento binário específico                          |
| /atualizar_documento/<documento_id> | PUT         | Atualiza informações de um documento binário                    |
| /memorias                     | POST, GET         | Cria (POST) ou lista (GET) memórias                            |
| /threads                      | GET               | Obtém as últimas threads (conversas) registradas no Passis     |


#### chathub.py

- Este arquivo é responsável pelo fluxo de mensagens e interações do usuário, gerenciando as mensagens recebidas e indicando as ações a serem tomadas com base no conteúdo da mensagem.
- O termo 'hub' se refere às múltiplas interações que este módulo do sistema realiza desde o recebimento das mensagens do _Webhook_, triagem das informações para entender a natureza do conteúdo (se áudio ou texto, por exemplo) e conexões com o modelo de linguagem e mensageria para que a resposta contextual seja enviada ao usuário.
- Existem comandos textuais específicos que são funcionais e permitem atuar diretamente no sistema, conforme listagem na tabela abaixo:
- 
- 
- 
- Funções de Suporte: Mencione funções de suporte como hora_e_data para manipulação de timestamps e envia_prompt_api para enviar prompts para a API do OpenAI.
context_gpt35turboFuncCalling.py

Descrição Geral: Introduza o arquivo context_gpt35turboFuncCalling.py como o responsável por criar contextos e responder perguntas usando o modelo GPT-3.5 Turbo.
Função create_context: Detalhe a função create_context, que cria um contexto relevante para uma pergunta específica.
Função answer_question: Explique a função answer_question, que utiliza o contexto criado para gerar respostas.
Função audio_transcription: Mencione a função audio_transcription para transcrição de áudios.
embeddings_db.py

Descrição Geral: Introduza o arquivo embeddings_db.py como o responsável pela atualização e gerenciamento de embeddings.
Função update_embeddings_db: Detalhe a função update_embeddings_db, que atualiza os embeddings no banco de dados.
Função atualiza_embedding: a função atualiza_embedding, que recupera dados de diferentes tabelas e atualiza os embeddings.
main.py

Descrição Geral: Introduza o arquivo main.py como o responsável por funções específicas de busca e processamento de dados.
Função nucleo_jogos: Detalhe a função nucleo_jogos, que busca informações sobre jogos de futebol.
Função busca_X: Explique a função busca_X, que utiliza a API do Google para buscar informações no Twitter.
Função busca_Clima: Mencione a função busca_Clima, que busca informações climáticas usando a API do Clima Tempo.
send_msg.py

Descrição Geral: Introduza o arquivo send_msg.py como o responsável pelo envio de mensagens via WhatsApp.
Função send_wapp_msg: Detalhe a função send_wapp_msg, que envia mensagens de texto.
Função send_wapp_question: Explique a função send_wapp_question, que envia perguntas interativas.
Função send_wapp_audio_reply: Mencione a função send_wapp_audio_reply, que envia respostas de áudio.
Falar do banco de dados passisdb
Falar do text-to-query
Mostrar como fico o contexto

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin pulvinar nisl vestibulum tortor fringilla, eget imperdiet neque condimentum. Proin vitae augue in nulla vehicula porttitor sit amet quis sapien. Nam rutrum mollis ligula, et semper justo maximus accumsan. Integer scelerisque egestas arcu, ac laoreet odio aliquet at. Sed sed bibendum dolor. Vestibulum commodo sodales erat, ut placerat nulla vulputate eu. In hac habitasse platea dictumst. Cras interdum bibendum sapien a vehicula. Proin feugiat nulla sem. Phasellus consequat tellus a ex aliquet, quis convallis turpis blandit. Quisque auctor condimentum justo vitae pulvinar. Donec in dictum purus. Vivamus vitae aliquam ligula, at suscipit ipsum. Quisque in dolor auctor tortor facilisis maximus. Donec dapibus leo sed tincidunt aliquam. 
![image](https://github.com/user-attachments/assets/28de962e-4340-4a5f-b690-49565f81d3e1)



### 3. Resultados
São surpreendentemente positivos os resultados da combinação de (i) dados públicos, utilizados para treinar os modelos fundacionais de larga escala, os (ii) dados pessoais, armazenados no banco de dados _passisdb_ e (iii) os dados em tempo real, recuperados no momento do uso da aplicação Passis. O assistente Passis foi utilizado experimentalmente  por cerca de um ano, enquanto aprimoramentos e novas funcionalidades foram sendo incorporadas.
As demonstrações dos resultados que se apresentam foram feitas utilizando o Whatsapp enquanto forma de interface de consulta. Para diferentes tipos de entrada, os resultados foram agrupados pela natureza do benefício gerado para o usuário.

#### 3.1 Ganhos de produtividade
- *Situação*: para realizar uma reserva de hotel, informações diversas tais como: nome completo, CPF, e-mail, endereço, data de nascimento etc. são solicitadas ao usuário;
- *Uso*: usuário insere as informações solicitadas no prompt de texto do Passis,  acrescidas de uma simples instrução que solicita o preenchimento dos campos;
- *Resultado*: as informações demandadas são selecionadas por similaridade semântica à partir dos registros contidos no banco de dados Passisdb. A busca vetorizada carrega as informações de maior correspondência no contexto que é passado para o modelo conversacional. O retorno da função é o texto preenchido que então é apresentado na tela do usuário conforme abaixo. 

![image](https://github.com/user-attachments/assets/4ffae721-ff99-401d-bd78-38b3a985684d)

- *Situação*: usuário necessita da data de expiração de seu passaporte;
- *Uso*: usuário solicita diretamente no prompt a informação desejada, mencionando o documento e o campo;
- *Resultado*: as informações demandadas são selecionadas por similaridade semântica e os documentos com maior correspondência são listados nas primeiras posições. Os metadados dos documentos de maior correspondência são passados para o modelo conversacional. Neste caso, em específico, a posição de memória do documento de maior relevância é guardada e enviada para uma segunda função que recupera a imagem do documento da memória. Tanto a resposta objetiva textual, quanto o documento de maior probabilidade de ocorrência, são apresentados ao usuário na tela do assistente.

![image](https://github.com/user-attachments/assets/91f9e5d8-9909-45d9-8649-4f6e7292d0d1)

- *Situação*: usuário dispõe de informação em formato de áudio (mp3, mp4, wav ou similar)
- *Uso*: usuário pode enviar diretamente ou encaminhar uma mensagem com conteúdo de áudio para o assistente
- *Resultado*: assistente recebe a mensagem e inicia a transcrição do áudio, que pode acontecer de forma multilíngue. Assistente retorna mensagem transcrita com duas opções: (i) memorizar aquela informação na memória de longo prazo ou tomar uma ação com o trecho de texto transcrito. Na sequência, o usuário pode selecionar no próprio assitente qual caminho deve ser seguido, dando continuidade a interação de forma escrita ou falada.

![image](https://github.com/user-attachments/assets/8c4c24b0-ab28-4043-afdf-cc23ca7e79bc)

#### 3.2 Ganhos de desempenho pessoal
- *Situação*: usuário precisa saber se tem sido bem sucedido na sua meta de acordar mais cedo
- *Uso*: usuário solicita ao assistente uma análise estatística sobre o horário que tem acordado indicando um horizonte de tempo determinado
- *Resultado*: as informações demandadas são direcionadas para o agente que é capaz de lidar com informações do tipo 'checkin' do usuário (busca_Checkin). Com base no texto enviado, o agente é capaz de extrair as datas de início e fim do período indicado e passá-las como argumento para a função que recupera as informações do banco de dados passisdb (tabela 'checkins'). Então, as informações são passadas para o modelo conversacional juntamente com outras informações de contexto, para permitir uma resposta completa e direcionada ao propósito pretendido. O assistente Passis retorna para a tela de interface as informações desejadas.
![image](https://github.com/user-attachments/assets/43a87420-3a7f-4bae-8f00-34b93302457b)

#### 3.3 Busca Geolocalizada em tempo real
- *Situação*: usuário precisa entender as oscilações térmicas pelas cidades por onde esteve cidades e temperaturas por onde estive
- *Uso*: usuário solicita ao assistente uma análise estatística sobre o horário que tem acordado indicando um horizonte de tempo determinado
- *Resultado*: as informações demandadas são direcionadas para o agente que é capaz de lidar com informações que envolvem clima e geolocalização (obter_cidade_atual_e_clima). Com base no texto enviado, o agente é capaz de extrair as datas de início e fim do período indicado e passá-las como argumento para a função que recupera as informações do banco de dados passisdb (tabela 'climas'). Então, as informações são passadas para o modelo conversacional juntamente com outras informações de contexto, para permitir uma resposta completa e direcionada ao propósito pretendido. O assistente Passis retorna para a tela de interface as informações desejadas.
![image](https://github.com/user-attachments/assets/dca56cf9-ec62-4bfc-8e14-cd7b9de22d19)
- *Situação*: usuário evita uma rota em razão de acidente ou evento acontecendo na cidade 
- *Uso*: usuário solicita ao assistente informações específicas sobre um local da cidade (túnel Rebouças no Rio de Janeiro)
- *Resultado*: as informações demandadas são direcionadas para o agente que é capaz de realizar buscas no X. Neste caso específico, é utilizado o perfil do Centro de Operações Rio (@OperacoesRio). Este agente retorna para a função uma lista com horários e acontecimentos ocorridos na cidade do Rio de Janeiro nas últimas horas. Com base nessas informações, o assistente Passis retorna, em forma de texto livre, uma mensagem correspondendo aos eventos solicitados.
![image](https://github.com/user-attachments/assets/3a641c20-3f75-4bbb-9eb4-30512733a08b)

#### 3.4 Busca em tempo real com preferências pessoais
Situação: usuário recebe informação em tempo real com base em suas preferências registradas em memória
Uso: usuário solicita ao assistente informações sobre jogos de futebol do dia seguinte, informando o apelido do seu time de futebol
Resultado: as informações demandadas são direcionadas para o agente _busca_Jogos_, que é capaz de buscar uma lista de jogos para um dia específico, além de saber inferir a data de interesse à partir do dia solicitado pelo usuário. Paralelamente, são ordenadas por similaridade as memórias relacionadas ao tema da pergunta; sendo neste caso um jogo de futebol, a primeira memória associada traz informações sobre o time de preferência do usuário. A função _main.get_jogos_ é então solicitada para a data de interesse e retorna a lista de jogos para a data informada enquanto argumento de entrada. Uma nova chamada é então realizada para o modelo de linguagem, que recebe a lista completa de jogos daquele dia, juntamente com as memórias relacionadas na primeira busca realizada neste processo. Com todas essas informações, o modelo retorna com as informações do jogo solicitado.
![image](https://github.com/user-attachments/assets/8cade159-71c8-4748-b33f-515a481ac719)

### 4. Conclusões
Dizer que o trabalho está alinhado com as melhores práticas e tendências do mercado, seja para uso dos dados, seja para aplicação dos conceitos de LLM.
- Assistentes LuzIA, Assistente Microsoft lançado no início de outubro...
- 

--- Matrícula: 123.456.789 Pontifícia Universidade Católica do Rio de Janeiro Curso de Pós Graduação *Business Intelligence Master*


### 5. Referências
##### Case Study: Human-Centric Generative AI Strategy - 15 May 2024 - ID G00811249 By Raf Gelders, Alicia Mullery, Sneha Ayyar - https://www.gartner.com/document/5431263?ref=solrResearch&refval=421781754&
##### The Future of Frontline Work: Collaborative Human-Machine Teams - 3 June 2024 - ID G00785847 By Emily Rose McRae, Manish Thigale, Kelsie Marian, Suzie Petrusic, Emily Potosky, Sam Grinter - https://www.gartner.com/document/4382299?ref=solrResearch&refval=421781754&
##### ([^3]) General Data Protection Regulation GDPR https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32016R0679
#### ([^4]) Edge Delta - estudo de dados - https://edgedelta.com/company/blog/how-much-data-is-created-per-day#:~:text=An%20internet%20user%20generates%20an%20average%20of%20146%2C880%20MB%20daily.&text=Researchers%20have%20stated%20that%20the,create%20about%20506%2C736%20MB%20daily.
#### [^7] Declaração do papel do assistente pessoal Passis, disponível em context_gpt35turboFuncCalling.py na linha 154 deste repositório
