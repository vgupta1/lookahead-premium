# Everything the paper prints, rebuilt from source data.
#
#   make all        every figure and table  (~1 min; uses the cached premium)
#   make test       the reproduction tests  (~40 s)
#   make portfolio  re-run the portfolio Monte Carlo from scratch (~2 h serial)
#   make clean      remove generated outputs, keep the caches
#
# LAP_ROOT and LAP_OUT override the repository root and the output directory,
# so the same scripts can write straight into a paper tree:
#   make all LAP_OUT=../manuscript_workshop/figs

PY      ?= python3
CODE    := code
OUT     ?= outputs
export LAP_OUT = $(abspath $(OUT))

.PHONY: all figures tables test test-fast portfolio paper clean help

all: figures tables

figures: $(OUT)/fig_shortest_path.pdf $(OUT)/fig_saa_normalized.pdf $(OUT)/fig_two_action.pdf
tables:  $(OUT)/tab_shift.tex $(OUT)/tab_portfolio.tex $(OUT)/tab_litaudit.tex \
         $(OUT)/tab_autopsy.tex

# Figure 1 and Figure 3, and the cost-shift table: one script, one pass over
# the Elmachtoub-Grigas shortest-path CSV.
$(OUT)/fig_shortest_path.pdf $(OUT)/fig_saa_normalized.pdf $(OUT)/tab_shift.tex: \
		$(CODE)/shortest_path_autopsy.py data/eg/shortest_path.csv
	$(PY) $(CODE)/shortest_path_autopsy.py --saa-figure --shift-table

$(OUT)/fig_two_action.pdf: $(CODE)/two_action_construction.py
	$(PY) $(CODE)/two_action_construction.py

# Table 4, rebuilt from the cached premium.  `make portfolio` recomputes it.
$(OUT)/tab_portfolio.tex: $(CODE)/portfolio_autopsy.py data/cache/portfolio_eta.csv \
		data/eg/portfolio.csv
	$(PY) $(CODE)/portfolio_autopsy.py --from-cache

# Table 1.
$(OUT)/tab_litaudit.tex: $(CODE)/literature_audit.py data/audit_workshop/audit.csv
	$(PY) $(CODE)/literature_audit.py

# Table 5 draws on both autopsies.
$(OUT)/tab_autopsy.tex: $(CODE)/make_autopsy_table.py $(CODE)/shortest_path_autopsy.py \
		$(CODE)/portfolio_autopsy.py data/cache/portfolio_eta.csv
	$(PY) $(CODE)/make_autopsy_table.py

# The one long computation.  Resumable: completed cells are appended to the cache
# as they finish, and re-running skips them.  --max-seconds bounds a single call.
portfolio:
	$(PY) $(CODE)/portfolio_autopsy.py --reps 50 --test 2000

test:
	$(PY) -m pytest -q

test-fast:
	$(PY) -m pytest -q -m "not slow"

clean:
	rm -f $(OUT)/*.pdf $(OUT)/*.tex $(OUT)/*.log
	rm -rf $(CODE)/__pycache__ tests/__pycache__ .pytest_cache

help:
	@sed -n '2,12p' Makefile

# Copy the regenerated exhibits into the paper tree: PDFs to figs/, tabulars to
# tables/.  The floats, captions and labels live in the .tex files and are not
# touched.
PAPER ?= ../manuscript_workshop
paper: all
	cp $(OUT)/*.pdf $(PAPER)/figs/
	cp $(OUT)/*.tex $(PAPER)/tables/
	@echo "copied into $(PAPER)"
