# SolarMiner Gateway CODE02 v0.6.251

## Intelligence bootstrap download reliability

- Increase the one-shot Intelligence bootstrap timeout from 15 minutes to two hours so a slow connection can finish the verified multi-gigabyte Ollama model download.
- Add a regression assertion for the bootstrap timeout.
- This improves tolerance for slow downloads; it does not prove a physical Gateway installation or resolve unrelated network/TLS failures.
