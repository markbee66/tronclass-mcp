# Development guardrails

- Never commit real credentials, temporary API entrypoints, local secret files, or machine-specific paths. Public examples must use placeholders and fake keys.
- Streamlit Ollama credentials belong only to the current session. Inject them explicitly into a new client for checks and answers. Never mutate process environment variables or cache clients carrying credentials across sessions.
- Keep secrets out of public Settings, repr, logs, exception messages, downloads, and evaluation results. Preserve endpoint and local-path export redaction, including upstream responses that echo connection details.
- Credential-bearing remote connections require HTTPS; literal localhost and loopback addresses may use HTTP. Reject URL credentials and never forward authorization through redirects.
- Test with fake credentials and mock HTTP services only. Never read personal secrets or call real paid services from tests.
- Preserve CLI/environment compatibility and Cloudflare Claude support. Keep provider=ollama for both local and remote connections. Connection UI work must not change inference limits, server rate limits, stream=false, or the System 1 flow.
- The remote Streamlit model is developer-controlled by REMOTE_OLLAMA_MODEL in tronclass/config.py, the sole runtime source. Display it read-only with no remote model input or selector. Connection checks must verify that exact model exists and fail clearly without fallback. Keep local Ollama and Cloudflare model controls. Do not add model restrictions to the API gateway.
- Add regression tests before implementation. Validate changes with the full pytest suite, evaluation dry-run, and git diff --check; inspect staged changes for sensitive data before committing.

User operation instructions belong in README.md.
