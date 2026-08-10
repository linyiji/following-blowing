# Multimodal provider documentation

Place the selected provider's official API documentation, request examples,
response examples, and error semantics in this directory. Provider adapters in
`app/providers/` are implemented from reviewed documentation; workflow agents
must never guess an API contract or call a provider SDK directly.

Do not place API keys, bearer tokens, or production response payloads containing
private data here.
