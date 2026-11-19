"""reason_guard unit tests, standard library only. Run: python3 -m unittest discover -s agent/tests"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest
from unittest import mock

try:  # inside the image, the installed copy
    from gateway.reason_guard import hook, labels, policy, screen
except ImportError:  # in the repository
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from reason_guard import hook, labels, policy, screen

B, P = policy.BROWSER, policy.PHONE

SHOP = """### Page
- Page URL: https://shop.example/cart
- Page Title: Cart
### Snapshot
```yaml
- main [ref=e1]:
  - heading "Your cart" [level=1] [ref=e2]
  - link "See details" [ref=e3] [cursor=pointer]
  - button "Place order" [ref=e4] [cursor=pointer]
  - button [ref=e5]:
    - img
    - text: Comprar agora
  - textbox "Pesquisar" [ref=e6]
  - generic [ref=e7]: Remover
```"""


def browser_saw(text, tool="browser_snapshot", args=None):
    screen.get().saw_browser(tool, args or {}, text)


def page(url, *nodes):
    body = "\n".join(f'  - {n} [ref=e{i + 10}]' for i, n in enumerate(nodes))
    return f"### Page\n- Page URL: {url}\n### Snapshot\n```yaml\n- main [ref=e9]:\n{body}\n```"


def decide(tool, **args):
    return policy.decide(tool, args, screen.get())


class Labels(unittest.TestCase):
    def test_categories(self):
        cases = {
            "Finalizar pedido": "purchase", "Comprar agora": "purchase", "Pagar R$ 25,90": "purchase",
            "Place order": "purchase", "Confirmar corrida": "purchase", "Assinar plano": "purchase",
            "Enviar": "send", "Send message": "send", "Post": "publish", "Publicar": "publish",
            "Excluir conta": "delete", "Cancelar assinatura": "delete", "Delete": "delete",
            "Pagar com código Pix": "purchase",  # buying is never exempted by a sign-in word
            "Finalizar pedido Código do cupom Aplicar": "purchase",
            "Postar " + "um texto bem longo sobre o produto e o código de desconto " * 2: "publish",
        }
        for label, category in cases.items():
            self.assertEqual(labels.classify(label), category, label)

    def test_harmless_and_sign_in(self):
        for label in ("Ver detalhes", "Postal code", "Facebook", "Buscar", "Enviar código", "Send code",
                      "Reenviar código por SMS", "Entrar", "Continuar com Google", "Próximo", "", "Notebook"):
            self.assertIsNone(labels.classify(label), label)


class Screen(unittest.TestCase):
    def setUp(self):
        screen.reset()

    def test_snapshot_refs_use_the_screen_text(self):
        browser_saw(SHOP)
        refs = screen.get().refs
        self.assertIn('button "Place order"', refs["e4"])
        self.assertIn("Comprar agora", refs["e5"])  # a nameless button gets the text under it
        self.assertEqual(screen.get().url, "https://shop.example/cart")

    def test_new_page_forgets_old_refs(self):
        browser_saw(SHOP)
        browser_saw(page("https://shop.example/thanks", 'heading "Thanks"'), "browser_click")
        self.assertNotIn("e4", screen.get().refs)

    def test_results_arrive_as_json(self):
        browser_saw(screen.texts(json.dumps({"result": SHOP})))
        self.assertIn("e4", screen.get().refs)

    def test_phone_list_text_and_json(self):
        text = ('One element per line: ...\n'
                '@e1 Button text="Pagar R$ 30" at=40,1100 size=640x120\n'
                '@e2 TextView text="Uber" label="Back" at=0,0 size=100x80')
        s = screen.get()
        s.saw_phone("mobile_list_elements_on_screen", text)
        self.assertIn("Pagar", s.phone_refs["@e1"])
        self.assertIn("Pagar", s.phone_label_at(300, 1150))
        self.assertEqual(s.phone_label_at(700, 700), "")
        s.saw_phone("mobile_swipe_on_screen", "Swiped")
        self.assertIsNone(s.phone_label_at(300, 1150))  # stale after an action
        items = [{"ref": "@e3", "type": "Button", "text": "Delete", "coordinates": {"x": 0, "y": 0, "width": 10, "height": 10}}]
        s.saw_phone("mobile_list_elements_on_screen", "Found these elements on screen: " + json.dumps(items))
        self.assertIn("Delete", s.phone_refs["@e3"])


class Policy(unittest.TestCase):
    def setUp(self):
        screen.reset()
        browser_saw(SHOP)

    def test_closed_list(self):
        self.assertEqual(decide("mcp__other__anything").action, policy.DENY)
        self.assertEqual(decide("terminal", command="ls").action, policy.DENY)
        self.assertEqual(decide("skill_manage").action, policy.DENY)
        self.assertEqual(decide("memory").action, policy.ALLOW)
        self.assertEqual(decide(B + "browser_snapshot").action, policy.ALLOW)

    def test_route_arounds_are_denied(self):
        for tool in ("browser_evaluate", "browser_run_code_unsafe", "browser_keydown", "browser_file_upload",
                     "browser_webmcp_call", "browser_network_requests"):
            self.assertEqual(decide(B + tool, function="() => 1").action, policy.DENY, tool)
        self.assertEqual(decide(B + "browser_navigate", url="javascript:alert(1)").action, policy.DENY)
        self.assertEqual(decide(B + "browser_navigate", url="file:///etc/passwd").action, policy.DENY)
        self.assertEqual(decide(B + "browser_navigate", url="https://shop.example").action, policy.ALLOW)

    def test_click_is_judged_by_the_screen_not_the_model(self):
        d = decide(B + "browser_click", target="e4", element="harmless link")
        self.assertEqual((d.action, d.category), (policy.ASK, "purchase"))
        self.assertIn("Place order", d.reason)
        self.assertEqual(decide(B + "browser_click", target="e5").action, policy.ASK)
        self.assertEqual(decide(B + "browser_click", target="e3", element="Place order").action, policy.ALLOW)

    def test_a_container_with_a_pay_button_inside_asks(self):
        browser_saw("- Page URL: https://shop.example/cart\n### Snapshot\n- generic [ref=e20]:\n"
                    '  - textbox "Código do cupom" [ref=e21]\n  - button "Finalizar pedido" [ref=e22]')
        self.assertEqual(decide(B + "browser_click", target="e20").category, "purchase")
        self.assertEqual(decide(B + "browser_click", target="e21").action, policy.ALLOW)

    def test_click_must_target_a_known_ref(self):
        self.assertEqual(decide(B + "browser_click", target="#buy").action, policy.DENY)
        self.assertEqual(decide(B + "browser_click", target="role=button[name=Pay]").action, policy.DENY)
        self.assertEqual(decide(B + "browser_click", target="e99").action, policy.DENY)
        self.assertEqual(decide(B + "browser_drag", startTarget="e4", endTarget="e99").action, policy.DENY)

    def test_sign_in_send_is_free_messages_are_not(self):
        browser_saw(page("https://accounts.example/login", 'button "Enviar"'))
        self.assertEqual(decide(B + "browser_click", target="e10").action, policy.ALLOW)
        browser_saw(page("https://mail.example/compose", 'button "Enviar"'))
        self.assertEqual(decide(B + "browser_click", target="e10").category, "send")

    def test_enter_submits(self):
        self.assertEqual(decide(B + "browser_type", target="e6", text="arroz", submit=True).action, policy.ALLOW)
        browser_saw(page("https://chat.example/c/1", 'textbox "Mensagem"'))
        self.assertEqual(decide(B + "browser_type", target="e10", text="oi", submit=True).category, "send")
        self.assertEqual(decide(B + "browser_type", target="e10", text="oi").action, policy.ALLOW)
        browser_saw("", "browser_type", {"target": "e10"})
        self.assertEqual(decide(B + "browser_press_key", key="Enter").category, "send")
        self.assertEqual(decide(B + "browser_press_key", key="ArrowDown").action, policy.ALLOW)
        browser_saw(page("https://shop.example/checkout/payment", 'textbox "CEP"'))
        self.assertEqual(decide(B + "browser_press_key", key="Enter").category, "purchase")

    def test_filling_is_not_committing(self):
        d = decide(B + "browser_fill_form", fields=[{"target": "e6", "name": "q", "type": "textbox", "value": "x"}])
        self.assertEqual(d.action, policy.ALLOW)
        self.assertEqual(decide(B + "browser_fill_form", fields=[{"target": "#q"}]).action, policy.DENY)

    def test_dialogs(self):
        self.assertEqual(decide(B + "browser_handle_dialog", accept=True).action, policy.DENY)  # unknown text
        browser_saw('### Modal state\n- ["confirm" dialog with message "Delete this address?"]: can be handled')
        self.assertEqual(decide(B + "browser_handle_dialog", accept=True).category, "delete")
        self.assertEqual(decide(B + "browser_handle_dialog", accept=False).action, policy.ALLOW)

    def test_phone(self):
        s = screen.get()
        s.saw_phone("mobile_list_elements_on_screen",
                    '@e1 Button text="Confirmar corrida" at=40,1100 size=640x120\n'
                    '@e2 Button text="Ver opções" at=40,900 size=640x120\n'
                    '@e3 View label="Deslize para pagar" at=40,1300 size=640x120')
        self.assertEqual(decide(P + "mobile_click_on_screen_at_coordinates", device="d", ref="@e1").category, "purchase")
        self.assertEqual(decide(P + "mobile_click_on_screen_at_coordinates", device="d", ref="@e2").action, policy.ALLOW)
        self.assertEqual(decide(P + "mobile_click_on_screen_at_coordinates", device="d", ref="@e9").action, policy.DENY)
        self.assertEqual(decide(P + "mobile_click_on_screen_at_coordinates", device="d", x=300, y=1150).action, policy.ASK)
        self.assertEqual(decide(P + "mobile_click_on_screen_at_coordinates", device="d", x=300, y=20).action, policy.DENY)
        self.assertEqual(decide(P + "mobile_drag_on_screen", device="d", fromRef="@e3", x2=700, y2=1360).action, policy.ASK)
        s.saw_phone("mobile_click_on_screen_at_coordinates", "Clicked")
        self.assertEqual(decide(P + "mobile_click_on_screen_at_coordinates", device="d", x=300, y=950).action, policy.DENY)
        self.assertEqual(decide(P + "mobile_open_url", device="d", url="intent://x").action, policy.DENY)
        self.assertEqual(decide(P + "mobile_install_app", device="d", path="/x.apk").action, policy.DENY)

    def test_every_exposed_tool_is_tagged(self):
        for name in policy.BROWSER_TOOLS:
            self.assertTrue(policy.known(B + name))
            self.assertNotIn(name, policy.BROWSER_DENIED)
        repo = pathlib.Path(__file__).resolve().parents[1] / "config" / "config.yaml"
        config = repo if repo.exists() else pathlib.Path("/opt/reason/config/config.yaml")
        text = config.read_text()  # the include lists in config.yaml are exactly the policy's lists
        browser = text.split("  browser:", 1)[1].split("# >>> phone", 1)[0]
        phone = text.split("# >>> phone", 1)[1].split("# <<< phone", 1)[0]
        listed = lambda block, prefix: sorted(l.strip()[2:] for l in block.splitlines() if l.strip().startswith("- " + prefix))
        self.assertEqual(listed(browser, "browser_"), policy.BROWSER_TOOLS)
        self.assertEqual(listed(phone, "mobile_"), policy.PHONE_TOOLS)


class Hook(unittest.TestCase):
    def setUp(self):
        screen.reset()

    def test_deny_and_allow_without_hermes(self):
        self.assertIn("BLOCKED", hook.directive("mcp__x__y", {})["message"])
        self.assertIsNone(hook.directive("memory", {}))

    def test_errors_fail_closed(self):
        with mock.patch.object(policy, "decide", side_effect=RuntimeError("boom")):
            self.assertEqual(hook.directive("memory", {})["action"], "block")

    def test_observe_never_raises(self):
        hook.observe(B + "browser_snapshot", None, object())
        hook.observe(B + "browser_snapshot", {}, SHOP)
        self.assertIn("e4", screen.get().refs)


if __name__ == "__main__":
    unittest.main()
