vermin:
	vermin . --eval-annotations --target=3.8 --violations fpgen/ || exit 1

clean:
	@echo Cleaning...
	find ./fpgen -type f ! -name "*.typed" ! -name "*.py" -exec rm -v {} \;
	rm -rf ./dist

prepare: vermin clean

check: prepare
	@echo Building...
	python -m build
	twine check dist/*

release: check
	@echo Releasing...
	twine upload dist/*
