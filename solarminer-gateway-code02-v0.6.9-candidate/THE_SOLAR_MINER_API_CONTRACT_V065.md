# Contrato API — emparelhamento e leitura v0.6.5

| Método | Endpoint | Autorização | Efeito |
|---|---|---|---|
| GET | `/api/v1/health` | Público | Health mínimo |
| GET | `/api/v1/info` | Público | Identificação do Gateway |
| GET | `/api/v1/status` | `read` | Estado do Gateway |
| GET | `/api/v1/energy/categories` | `read` | Categorias |
| GET | `/api/v1/energy/equipment` | `read` | Equipamentos e leituras disponíveis |
| GET | `/api/v1/energy/equipment/{equipment_id}` | `read` | Detalhe de equipamento |
| POST | `/api/v1/devices/pairing-codes` | Sessão válida + `manage_devices` | Código aleatório de uso único para username ativo; TTL 60–600 s |
| POST | `/api/v1/devices/pair` | Código temporário + assinatura Ed25519 | Cria dispositivo/associação numa transação |
| POST | `/api/v1/auth/login` | Password + assinatura de dispositivo associado | Sessão opaca de 8 h |
| POST | `/api/v1/auth/logout` | Sessão autenticada | Revoga sessão |

## Canonicals

- Pairing: `PAIR\n{pairing_code}\n{sha256(public_key_spki_der)}\n{NORMALIZED_MAC}\n{timestamp}\n{nonce}`.
- Login legado preservado: `LOGIN\n{username}\n{device_id}\n{timestamp}\n{nonce}`.

Timestamps são aceites dentro de ±300 segundos. Nonces são consumidos no servidor com restrição única. O código de pairing é armazenado como SHA-256 e só pode ser usado uma vez. A associação não altera o role do utilizador. MAC é declarado, não verificado fisicamente.

A API não tem refresh de sessão nem endpoint geral de comando. O token é limitado, armazenado por hash no servidor e apenas em memória na PWA. TLS é necessário para proteger a password e o token em trânsito.
