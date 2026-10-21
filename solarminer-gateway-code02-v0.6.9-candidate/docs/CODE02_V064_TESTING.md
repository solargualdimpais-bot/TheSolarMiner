# CODE 02 v0.6.4 — testes locais

Executar no checkout:

```sh
PYTHONPATH=src python3 -m pytest -q
```

O teste de baseline deve ser feito sobre o ZIP v0.6.3 preservado, sem alterações. Os testes v0.6.4 cobrem chamadas worker para TCP probe, negação de destinos/portas inválidos, recuperação simulada de ponteiro bloqueio seguro quando o caminho ativo não é um symlink, e entrega same-origin da PWA por HTTP de teste.

Os testes não validam enforcement de systemd, isolamento de UID, conectividade com equipamentos reais, consistência de uma transação multi-recurso ou recuperação após perda real de energia.
