# Gateway 0.6.213

- Deye polling now waits one measured read latency after each successful response, with the interval starting when that response arrives.
- A failed read retries after five times the last successful read latency.
- Latency is measured internally and is not added to the API response.
- Persisting the received sample no longer extends the wait before the next request.
