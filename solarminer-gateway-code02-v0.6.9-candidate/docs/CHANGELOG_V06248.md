# SolarMiner Gateway CODE02 v0.6.248

## Fix

- Create the `solarminer-intelligence` system group and service account during Debian package configuration before assigning ownership of the Intelligence state directory. This prevents the package `postinst` script from failing on a clean Debian installation.
