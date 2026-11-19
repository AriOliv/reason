"""What an element does, from its visible label: buy, send, delete, publish, or nothing risky.

The label always comes from the screen (see ``screen``), never from how the model describes
the element. Matching is on whole words, case- and accent-insensitive, in Portuguese, English
and Spanish. Signing in stays free: "send code", "enviar código" and the like are not risky,
because asking the owner for a login code is the point of the product. Buying and deleting
are never exempted ("Pagar com código Pix" is a payment).
"""

from __future__ import annotations

import re
import unicodedata

# Category -> phrases. A phrase matches as whole words; "*" at the end matches a word prefix.
RISKY: dict[str, tuple[str, ...]] = {
    "purchase": (
        # pt
        "comprar", "compre", "finalizar compra", "finalizar pedido", "fazer pedido", "fechar pedido",
        "confirmar pedido", "confirmar compra", "confirmar pagamento", "pagar", "pague", "efetuar pagamento",
        "assinar", "assine", "contratar", "reservar", "confirmar reserva", "pedir agora", "doar",
        "transferir", "enviar pix", "pagar com pix", "solicitar corrida", "confirmar corrida",
        "confirmar viagem", "chamar uber", "adicionar saldo", "recarregar",
        # en
        "buy", "buy now", "purchase", "pay", "pay now", "place order", "place your order", "confirm order",
        "complete order", "complete purchase", "submit order", "order now",
        "book", "book now", "reserve", "confirm booking", "confirm reservation", "subscribe",
        "start subscription", "upgrade", "donate", "transfer", "send money", "request ride", "confirm ride",
        "confirm pickup", "add funds", "top up",
        # es
        "pagar ahora", "realizar pedido", "confirmar compra", "suscribirse", "suscribir", "reservar ahora",
        "donar", "transferir dinero", "solicitar viaje",
    ),
    "send": (
        "enviar", "envie", "mandar", "responder a todos", "send", "send message", "reply all", "forward",
        "encaminhar", "reenviar mensagem", "submit", "enviar formulario", "enviar solicitacao",
    ),
    "publish": (
        "publicar", "postar", "post", "tweet", "tweetar", "share", "compartilhar", "compartir", "repost",
        "retweet", "go live", "comentar", "comment", "avaliar", "enviar avaliacao", "submit review",
    ),
    "delete": (
        "excluir", "exclua", "apagar", "apague", "deletar", "delete", "remove account", "excluir conta",
        "encerrar conta", "close account", "deactivate", "desativar conta", "cancelar assinatura",
        "cancel subscription", "cancelar pedido", "cancel order", "cancelar reserva", "cancel booking",
        "cancelar plano", "cancel plan", "eliminar", "borrar", "empty trash", "esvaziar lixeira",
    ),
}

# Words that make a short "send"/"publish" label a sign-in step instead (see classify).
SAFE: tuple[str, ...] = (
    "codigo", "code", "codigos", "verificacao", "verification", "verify", "verificar", "otp", "sms",
    "entrar", "login", "log in", "sign in", "signin", "iniciar sesion", "acessar", "continuar com",
    "continue with", "senha", "password", "link magico", "magic link", "reenviar codigo", "resend",
    "send again", "enviar novamente", "enviar de novo", "pesquisar", "search", "buscar", "filtrar",
)

VERBS = {
    "pt": {"purchase": "Comprar / pagar", "send": "Enviar", "publish": "Publicar", "delete": "Apagar / cancelar"},
    "en": {"purchase": "Buy / pay", "send": "Send", "publish": "Publish", "delete": "Delete / cancel"},
    "es": {"purchase": "Comprar / pagar", "send": "Enviar", "publish": "Publicar", "delete": "Borrar / cancelar"},
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _pattern(phrases: tuple[str, ...]) -> re.Pattern[str]:
    parts = []
    for phrase in phrases:
        prefix = phrase.endswith("*")
        words = normalize(phrase.rstrip("*")).split()
        body = r"\s+".join(re.escape(w) for w in words)
        end = "" if prefix else r"\b"
        parts.append(r"\b" + body + end)
    return re.compile("|".join(parts))


_RISKY = {category: _pattern(phrases) for category, phrases in RISKY.items()}
_SAFE = _pattern(SAFE)


# The sign-in exemption only applies to short labels (one control's text, like "Enviar código"),
# never to a container whose text happens to include a sign-in word next to a "Pay" button.
SAFE_MAX_CHARS = 60


def classify(label: str) -> str | None:
    """The risky category of an element label ("purchase", "delete", "send", "publish") or None.

    Buying and deleting are never exempted. "Send"/"publish" words are exempted on short labels
    about signing in or verifying ("Enviar código", "Send code"), so logging in stays free.
    """
    text = normalize(label)
    if not text:
        return None
    for category in ("purchase", "delete"):
        if _RISKY[category].search(text):
            return category
    for category in ("send", "publish"):
        if _RISKY[category].search(text):
            if len(text) <= SAFE_MAX_CHARS and _SAFE.search(text):
                return None
            return category
    return None


def verb(category: str, language: str = "pt") -> str:
    return VERBS.get(language, VERBS["en"]).get(category, category)
