#!/bin/bash
# run_notebook.sh
# Executes a Jupyter notebook and saves outputs so Claude can read them
# without manual copy-pasting.
#
# Usage:
#   ./run_notebook.sh                          # runs VRTPP_PR_Optimization.ipynb
#   ./run_notebook.sh VRTPP-PaperModel.ipynb   # runs a specific notebook
#
# Outputs:
#   <notebook>_executed.ipynb   full notebook with all cell outputs
#   <notebook>_outputs.txt      plain text of every cell's output (for quick reading)

JUPYTER=/Users/ariel/miniconda3/bin/jupyter
NOTEBOOK="${1:-VRTPP_PR_Optimization.ipynb}"
BASE="${NOTEBOOK%.ipynb}"
OUTPUT_NB="${BASE}_executed.ipynb"
OUTPUT_TXT="${BASE}_outputs.txt"

echo "=== run_notebook.sh ==="
echo "Notebook : $NOTEBOOK"
echo "Started  : $(date)"
echo ""

"$JUPYTER" nbconvert \
  --to notebook \
  --execute \
  --output "$OUTPUT_NB" \
  --ExecutePreprocessor.timeout=7200 \
  "$NOTEBOOK"

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo ""
  echo "FAILED (exit $EXIT_CODE). Partial outputs (if any) are in $OUTPUT_NB."
  exit $EXIT_CODE
fi

echo ""
echo "Finished : $(date)"
echo "Saved    : $OUTPUT_NB"

# Extract plain-text outputs to a .txt file for Claude to read
python3 - "$OUTPUT_NB" "$OUTPUT_TXT" << 'PYEOF'
import json, sys, re

nb_path, txt_path = sys.argv[1], sys.argv[2]

with open(nb_path) as f:
    nb = json.load(f)

def strip_ansi(s):
    return re.sub(r'\x1b\[[0-9;]*m', '', s)

lines = []
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] != 'code':
        continue
    outputs = cell.get('outputs', [])
    if not outputs:
        continue
    lines.append(f'=== Cell {i} ===')
    for out in outputs:
        otype = out.get('output_type', '')
        if otype == 'stream':
            text = ''.join(out.get('text', []))
        elif otype in ('display_data', 'execute_result'):
            text = ''.join(out.get('data', {}).get('text/plain', []))
        elif otype == 'error':
            text = f"ERROR {out.get('ename','')}: {out.get('evalue','')}\n"
            text += strip_ansi(''.join(out.get('traceback', [])))
        else:
            continue
        lines.append(strip_ansi(text).rstrip())

with open(txt_path, 'w') as f:
    f.write('\n'.join(lines) + '\n')

print(f'Text outputs saved to {txt_path}')
PYEOF
