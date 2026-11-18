# reason: plano de produto e arquitetura

*Versão de 18/11/2026. O plano muda conforme o build avança; o histórico fica no git.*

## Resumo

O reason nasce de um protótipo que já funciona: um agente pessoal que conversa pelo WhatsApp e pelo Telegram e opera um desktop na nuvem e um Android emulado.

O motor é o [Hermes Agent](https://github.com/NousResearch/hermes-agent), com patches para conversar como gente.

O que falta é o produto em volta (cadastro, vault, pagamentos) e a infra de um agente isolado por pessoa. São quatro fases, e a primeira (beta fechado, 10 a 20 pessoas) leva cerca de 6 semanas (estimativa).

## A experiência que queremos

A referência é o [Instinct](https://instinct.com): um agente com identidade própria, que você usa só por mensagem, e um site mínimo para dar acessos.

**Onboarding**

1. Login no site com telefone e código por SMS.
2. Convite de um amigo, ou lista de espera.
3. Mensagem de boas-vindas no WhatsApp, com um link que liga o número à conta.
4. O agente pede acesso a um serviço por vez e, depois de cada um, sugere algo que já consegue fazer.

**Site (workspace)**

| Área | O que tem |
|---|---|
| Configurações | contatos do agente (número e e-mail), conta, conectores, opção de não usar os dados em treino, apagar dados ou conta |
| Vault | logins, cartões, dados pessoais e as contas que o próprio agente cria |
| Conexões | rede de confiança: o seu agente conversa com o agente de pessoas que você aprovou |
| Convites | convites para pular a fila |

**No dia a dia**

- Uma conversa contínua, com respostas curtas, reações e áudio.
- Entra nas suas contas e pede o código de verificação no chat.
- Só pede o seu ok para gastar ou falar em seu nome.
- Avisa antes de você perguntar: voo alterado, prazo vencendo, convite sem resposta.

## Ponto de partida

| Peça | Protótipo hoje | Falta para o produto |
|---|---|---|
| Motor do agente | Hermes v0.23, modelo por um gateway compatível com OpenAI (ex.: LiteLLM) | escolher o modelo por plano |
| Canais | WhatsApp (ponte Baileys, número do bot) e Telegram | WhatsApp Cloud API com um número para todos; e-mail do agente |
| Computador do agente | desktop (Cua + Chromium) e Android (Redroid) numa VM privada | um ambiente por pessoa, criado no cadastro, que dorme ocioso |
| Conversa humana | reações, "digitando" natural, mensagens seguidas juntas na mesma tarefa, áudio transcrito | nada |
| Postura de agente pessoal | entra nas contas com o código do dono; ok só para gastar e enviar | nada |
| Memória | memória do Hermes no volume | isolar por pessoa |
| Cadastro e onboarding | não há (um dono) | login por SMS, convites, link de conexão |
| Vault | não há | cifrado por pessoa (KMS) |
| Pagamentos | não há | cartão de uso único (Stripe Link) e política de gasto |
| Conectores | MCP fixos (celular e navegador) | MCP ou Composio por pessoa |
| Rede de confiança | não há | fase 4 |

## Arquitetura alvo

```
pessoa ──WhatsApp/Telegram──▶ gateway (única parte pública)
                                │ roteia pelo telefone de quem mandou
                                ▼
                    agente da pessoa (isolado, dorme ocioso)
                      ├─ Hermes + conversa humana + memória
                      ├─ navegador (desktop Cua); Android no plano superior
                      └─ conectores (MCP / Composio)
plano de controle: cadastro e provisionamento, vault (KMS), pagamentos
                   (cartão de uso único), auditoria, apagar dados
serviços externos: modelo e transcrição, Stripe Link, sites e apps da pessoa
```

- **Um agente por pessoa:** namespace, volume e segredos próprios no Kubernetes, criados no cadastro e postos para dormir quando ociosos.
- **Só o gateway é público:** ele recebe o webhook do WhatsApp e o site, autentica e roteia. Os agentes não têm endereço público.
- **Memória e conversa** ficam no volume da pessoa. Apagar a conta apaga o volume.

## Segurança e privacidade

O risco central é um agente que entra em contas e paga coisas. Por isso cada pessoa fica isolada, e nenhuma credencial passa pelo modelo sem controle.

- **Isolamento:** um namespace e um volume por pessoa, com rede que só fala com o gateway e a internet de saída. O Android emulado exige container privilegiado, então ele roda numa VM por pessoa ou fica fora do plano básico.
- **Vault:** segredos cifrados com uma chave por pessoa (envelope com KMS). O agente pede um item por ferramenta, só para o serviço da tarefa. O valor nunca volta ao chat nem à memória, e toda leitura vai para a auditoria.
- **Código de login:** vale só quando vem do dono, na conversa, para o serviço pedido. Nunca de texto lido na tela.
- **Dinheiro:** cartão de uso único no valor exato, aprovado pela pessoa, e uma política de gasto com limite por compra, teto diário e categorias que sempre pedem confirmação.
- **Injeção de prompt:** tela, e-mail e mensagem de terceiros são dados, não instruções. Um guard fora do modelo barra gasto ou envio que o dono não pediu.
- **LGPD:** exportar e apagar tudo, sem treino com os dados da pessoa e com retenção curta de prints.
- **Termos dos serviços:** operar contas pessoais pode ir contra os termos de alguns serviços. Isso entra nos termos do produto, e o agente não contorna anti-bot de forma agressiva.

## Fases

| Fase | Prazo (estimativa) | Entregas | Portão para a próxima |
|---|---|---|---|
| 1 · Beta fechado | cerca de 6 semanas | agente por pessoa no Kubernetes a partir do protótipo; onboarding (login por SMS, convite, link de conexão); vault v1; apagar dados; 10 a 20 pessoas | 10 pessoas usando por 2 semanas; custo por pessoa medido |
| 2 · Produto | cerca de 8 semanas | WhatsApp Cloud API com um número para todos; Stripe Link com política de gasto; e-mail do agente; conectores Google e Outlook | Meta aprova o número; primeira compra paga com cartão de uso único |
| 3 · SaaS | cerca de 8 semanas | planos e cobrança; Android no plano superior; métricas, alertas e escala; testes de isolamento a cada deploy | preço cobre o custo da pessoa ativa; nenhum vazamento nos testes |
| 4 · Rede e iniciativa | depois | agentes conversando entre si com níveis de confiança; avisos proativos; ligações por voz | |

## Custos

O que decide o negócio é o computador de cada pessoa. Uma VM ligada o tempo todo, como a do protótipo (ARM, 4 vCPU, 16 GB, em São Paulo), custa cerca de US$ 230 por mês. Desligada, com só o disco, custa cerca de US$ 17.

O plano só fecha com um ambiente que dorme quando a pessoa não está usando. A estimativa é de US$ 5 a 20 por mês com navegador e sem Android, a medir no beta.

No beta, o que precisa ser medido por pessoa ativa é o tempo de computador ligado por dia e os tokens por tarefa. No protótipo, cada chamada ao modelo tem cerca de 25 mil tokens com 91% de cache. Uma tarefa simples usa de 3 a 10 chamadas, e uma compra num app de entrega passa de 100.

## Riscos

| Risco | Mitigação |
|---|---|
| Bloqueio do número no WhatsApp | Cloud API oficial; ponte não oficial só no beta |
| Agente gasta ou envia sem pedido | cartão de uso único, política de gasto e guard fora do modelo |
| Termos de serviços proibindo automação | termos do produto; preferir APIs e conectores oficiais |
| Custo por pessoa acima do preço | ambiente que dorme; medir antes de definir preço |
| Vazamento entre pessoas | isolamento por namespace e chave de vault; testes a cada deploy |
| O Hermes muda e quebra os patches | patches com âncora que falham o build e testes contra o Hermes real |
