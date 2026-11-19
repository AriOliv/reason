"""reason_guard: the policy guard, in code, before every tool call.

Installed into the Hermes image as ``gateway/reason_guard`` and wired in by
``patches/apply.py`` into the one place every tool call passes through
(``hermes_cli.plugins._get_pre_tool_call_directive_details``), ahead of any plugin.
Pure standard library, so the unit tests run outside the image.

Modules
    labels  what a button, link or element *does*: buy, send, delete, publish (or nothing risky)
    screen  what the agent last saw: the browser snapshot (ref -> label, page URL, dialog) and
            the phone's element list, learned from tool results, never from the model's words
    policy  every tool the agent has, tagged, and the decision for one call: allow / ask / deny
    hook    the glue with Hermes: fails closed, refuses to auto-approve, unique approval per call

The guard has no switch. It is the product's safety floor, not a behaviour.
"""
