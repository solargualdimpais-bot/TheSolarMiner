# Gateway 0.6.217

- Applies the agreed Owner decision as two outcomes: preserve an active Owner only after verifying its Argon2 password hash; otherwise reset the dedicated data volume and configure a new Owner.
- Initializes a labeled `SOLARMINER_DATA` volume when it cannot be mounted or its filesystem/Owner cannot be identified, removing known signatures before creating ext4.
- Keeps the root/system partition out of the data-volume reset path and refuses to reset a data volume mounted somewhere other than the expected data mount.
- Adds regression tests for signature-bearing and interrupted data partitions and the Owner decision flow.
