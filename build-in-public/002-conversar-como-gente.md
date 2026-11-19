# 002 · Primeiro código: conversar como gente

*18/11/2026 · rascunho*

## O que aconteceu

- Saiu a primeira peça de código do reason: a imagem do agente, em cima do Hermes Agent.
- Comparei com o open-instinct, lendo o código dele, e decidi o caminho:
  - a camada de regras deles é melhor que a minha: barreira em código antes de cada ferramenta e aprovação presa à chamada exata;
  - mas o cartão de uso único volta ao modelo em texto puro, a mesma chave da operação vai para a VM de cada cliente e o agente clica por coordenada de pixel;
  - fica a infra e a conversa daqui, e as ideias de regras de lá, já corrigidas (issues #8 a #13).
- A memória vai ser o Supermemory self-hosted, uma instância por pessoa, sem nenhuma porta aberta para a internet (#14).
- O código é escrito do zero, e 25 testes rodam dentro da imagem, contra o Hermes de verdade. Se um teste falha, a imagem nem sai.

## Post no X (fio)

**1/5**
Primeiro código do reason, o Instinct open source.

Não é o agente fazendo tarefa.
É ele conversando como gente.

**2/5**
O que mudou:
👀 na sua mensagem enquanto ele trabalha.
Some quando termina.
"Valeu" vira só um ❤️, sem texto.

**3/5**
"Digitando" só quando a resposta está pronta.
Não durante 1 minuto de tarefa.
E por um tempo do tamanho da mensagem.

**4/5**
Você manda "compra salgadinho" e depois "doritos e água".
Ele junta as duas na mesma tarefa.
Não pergunta o que você já disse.

**5/5**
25 testes rodam dentro da imagem, contra o Hermes de verdade.
Se um falha, a imagem nem sai.

Próximo: o computador do agente.

github.com/AriOliv/reason

## Post no LinkedIn

Primeiro código do reason, o Instinct open source que estou construindo em público.

Antes de escrever, fui ler o código do open-instinct, o clone aberto mais conhecido.
A camada de regras dele é melhor que a minha:
uma barreira em código antes de cada ação do agente,
e aprovação presa à ação exata.

Mas achei três problemas:
o número e o CVC do cartão voltam para o modelo em texto,
a mesma chave da operação vai para a máquina de cada cliente,
e o agente clica por coordenada de pixel.

Então o caminho ficou assim:
a infra e a conversa ficam daqui,
as ideias de regras vêm de lá, já corrigidas.

E a primeira peça foi a menos óbvia:
fazer o agente conversar como gente.

👀 na sua mensagem enquanto ele trabalha.
"Valeu" vira só um ❤️.
"Digitando" só quando a resposta está pronta.
E duas mensagens seguidas viram uma tarefa só.

São 25 testes rodando dentro da imagem, contra o Hermes de verdade.
Se um falha, a imagem nem sai.

Próximo passo: o computador do agente.

github.com/AriOliv/reason
