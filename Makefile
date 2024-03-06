FUNC_NAME=verify_sender

.PHONY: find_python_user_dir install install_dev source clean lint test lambda_invoker zip sonar-zip func-name zip-name build deploy

find_python_user_dir:
	$(eval PYTHON_LOCAL_BIN = $(shell python3 -m site --user-base)/bin)

install: source
	LANG="en_US.UTF-8" python3 -m pipenv install --deploy

install_dev: source
	LANG="en_US.UTF-8" python3 -m pipenv install --dev

source:
	PIPENV_INSTALL_VERSION="`if [ -z $${PIPENV_INSTALL_VERSION} ]; then echo ""; else echo "==$${PIPENV_INSTALL_VERSION}"; fi`"; \
		python3 -m pip install --user pipenv$${PIPENV_INSTALL_VERSION}

clean: find_python_user_dir
	$(PYTHON_LOCAL_BIN)/pipenv --rm
	rm -rf .venv build __pycache__ .pytest_cache .coverage $(FUNC_NAME).zip

lint: find_python_user_dir
	mkdir -p build
	rm -f build/$(FUNC_NAME)_lint_report.txt
	$(PYTHON_LOCAL_BIN)/pipenv run python3 -m flake8 --exit-zero --exclude .venv,build,__pycache__  --filename=**/*.py --output-file=build/$(FUNC_NAME)_lint_report.txt
	$(PYTHON_LOCAL_BIN)/pipenv run flake8_junit build/$(FUNC_NAME)_lint_report.txt build/$(FUNC_NAME)_lint_report_junit.xml
	cat build/$(FUNC_NAME)_lint_report.txt
	@echo

test: find_python_user_dir
	mkdir -p build
	$(PYTHON_LOCAL_BIN)/pipenv run python3 -m pytest --junitxml=build/$(FUNC_NAME)_report.xml --cov $(FUNC_NAME) --cov-report term-missing --cov-report xml:build/coverage.xml --cov-report json:build/coverage.json

lambda_invoker: find_python_user_dir
	$(PYTHON_LOCAL_BIN)/pipenv run python3 lambda_invoker.py $(TARGET)

zip:
	zip -r $(FUNC_NAME).zip $(FUNC_NAME).py

sonar-zip:
	zip -r sonar-deps.zip build/

func-name:
	@echo $(FUNC_NAME)

zip-name:
	@echo $(FUNC_NAME).zip

build: clean install_dev lint test

deploy: clean install zip
