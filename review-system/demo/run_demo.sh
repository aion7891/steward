#!/usr/bin/env bash
# Steward end-to-end demo on a FAKE folder (never touches your real files).
# Usage (from the project root):  bash review-system/demo/run_demo.sh
# Needs: uv, Ollama running with `gemma4` and `nomic-embed-text` pulled.
set -u
DEMO="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DEMO/../.." && pwd)"
cd "$DEMO"
rm -rf data chroma knowledge reports          # start clean (demo folder only)

st() { uv run --project "$ROOT" steward --config config.demo.yaml "$@" 2>&1 | grep -v -e "^INFO" -e "Registry"; }
step() { printf '\n\033[1;34m==== %s\033[0m\n' "$1"; }

step "1. Create the sample folder";            uv run --project "$ROOT" python create_sample_folder.py
step "2. Health check";                         st --check
step "3. Scan (first time: hashes everything)"; st --scan
step "4. Scan again (nothing changed: hashes 0)"; st --scan
step "5. Detect installed apps";                st --software
step "6. Read a PDF";                           st --read sample_home/Documents/Acme/invoice-q3.pdf
step "7. Try to read the secret .env";          st --read sample_home/Documents/.env
step "8. Build the search index (Ollama embeddings)"; st --index
step "9. Semantic search";                      st --search "how much money is due on the invoice"
step "10. Build the OKF knowledge notebook";    st --build-okf
step "11. Search the notebook";                 st --okf-search "acme invoice"
step "12. Recommendations";                     st --recommend
step "13. Weekly report (md + html)";           st --report both
step "14. Cleanup workflow (dry-run proposals)"; st --workflow cleanup
step "15. Actions table";                       sqlite3 -header -column data/steward.db "select id, action_type, status, dry_run, reason from actions"
step "16. Ask the AI (gemma4, ~30-60 s)";       st --chat "How much is due on the Acme invoice? Cite the file."

printf '\nDone. Now open these to SEE the results:\n'
printf '  %s\n' "$DEMO/knowledge/index.md" "$DEMO/reports/" "$DEMO/data/steward.db" "$DEMO/data/logs/steward.log"
