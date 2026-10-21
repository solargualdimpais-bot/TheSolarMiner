PYTHON ?= python3
OUT ?= dist
PACKAGE = $(OUT)/solarminer-gateway_0.6.9_amd64.deb

.PHONY: test deb clean

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

deb:
	./packaging/build-deb.sh "$(abspath $(OUT))"

test-package: deb
	dpkg-deb --info "$(PACKAGE)"
	dpkg-deb --contents "$(PACKAGE)"

clean:
	rm -rf .pytest_cache src/solarminer_gateway/__pycache__ tests/__pycache__
