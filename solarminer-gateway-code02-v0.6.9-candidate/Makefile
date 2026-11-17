PYTHON ?= python3
OUT ?= dist
PACKAGE_VERSION = $(shell sed -n 's/^Version: //p' packaging/control)
PACKAGE = $(OUT)/solarminer-gateway_$(PACKAGE_VERSION)_amd64.deb

.PHONY: test deb test-package clean

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

deb:
	sh ./packaging/build-deb.sh "$(abspath $(OUT))"

test-package: deb
	dpkg-deb --info "$(PACKAGE)"
	dpkg-deb --contents "$(PACKAGE)"

clean:
	rm -rf .pytest_cache src/solarminer_gateway/__pycache__ tests/__pycache__


