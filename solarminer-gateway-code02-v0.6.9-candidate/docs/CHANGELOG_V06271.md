# SolarMiner Gateway CODE02 v0.6.271

- Drain stale socket-activated administrative terminal sessions from earlier releases during package upgrade, then reopen the listener; retain bounded Bash process-group cleanup for new sessions.
- Normalize the Intelligence agent's in-progress status so the Gateway accepts the correlated trace and reports the existing credential as accepted instead of marking the whole trace unavailable.
- Keep the user prompt, credentials, SDK response text, Ollama, Qwen, OpenClaude, MCP, and inference deadlines unchanged.