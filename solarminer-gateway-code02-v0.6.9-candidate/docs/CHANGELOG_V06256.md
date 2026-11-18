# SolarMiner Gateway CODE02 v0.6.256

- Reports Ollama executable installation separately from whether its local API responds.
- When the Gateway status request fails, the Owner Intelligence panel labels component state as unknown instead of implying that Ollama, its model, or OpenClaude is absent.
- The model remains reported as unknown when Ollama is installed but its API cannot be queried; the UI does not infer that the model is missing.
