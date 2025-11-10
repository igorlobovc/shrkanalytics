.PHONY: pipeline summaries audit normalize providers files explicit_terms explicit_by_sheet catalog

pipeline:
	python3 Estelita/run_full_pipeline.py

summaries:
	python3 Estelita/build_value_rollups.py
	python3 Estelita/build_fornecedores_summaries.py || true
	python3 Estelita/build_unified_summaries.py
	python3 Estelita/build_providers_summary.py
	python3 Estelita/build_files_summary.py

audit:
	python3 Estelita/build_searchable_base.py
	python3 Estelita/audit_search_coverage.py || true
	python3 Estelita/build_explicit_counts_by_sheet.py

normalize:
	python3 Estelita/normalize_fornecedores.py

providers:
	python3 Estelita/build_providers_summary.py

files:
	python3 Estelita/build_files_summary.py

explicit_terms:
	python3 Estelita/build_explicit_terms_index.py

explicit_by_sheet:
	python3 Estelita/build_explicit_counts_by_sheet.py

catalog:
	python3 Estelita/build_data_catalog.py

