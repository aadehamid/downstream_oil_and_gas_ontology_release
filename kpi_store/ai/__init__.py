"""The AI option of the propose command (KPI-DEC-0002, Q16 to Q20, Q22 and Q26).

AI is off by default. A person switches it on for one form with `python -m kpi_store.propose --ai <form>`, and only
when the local settings name a provider that the client's IT has approved ([ai] in the local settings file,
kpi_store/local_settings.py). What the AI writes is only ever a suggestion. The person accepts or rejects each one,
the signers sign the answers as they then stand, and the rule-based propose checks them as it checks every form.

    providers.py   the providers: a model served in the client's Databricks workspace, the Anthropic Messages API,
                   OpenAI chat completions, and by hand (any assistant, such as Genie Code, that the person gives
                   the prompt to). The standard library makes each call.
    suggest.py     the suggestions for a form's free-text answers: the prompt, the strict check of the answer,
                   the person's choices, and the record of the AI step that the proposal and the approval record keep.

Each provider gets the release's own skills as its instructions (Q26), read from skills/ at run time.
"""


class AIRefused(Exception):
    """The AI step cannot run, or its answer cannot be used. The message says why in a plain sentence. Nothing
    was changed."""
