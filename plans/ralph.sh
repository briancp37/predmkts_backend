#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <iterations> [release] [sprint]"
  exit 1
fi

# Set file paths based on optional release/sprint parameters
if [ -n "$2" ] && [ -n "$3" ]; then
  PRD_FILE="plans/releases/$2/sprints/$3/prd.json"
  PROGRESS_FILE="plans/releases/$2/sprints/$3/progress.txt"
else
  PRD_FILE="plans/prd.json"
  PROGRESS_FILE="progress.txt"
fi

echo "Using PRD: $PRD_FILE"
echo "Using Progress: $PROGRESS_FILE"

# Verify files exist
if [ ! -f "$PRD_FILE" ]; then
  echo "Error: PRD file not found: $PRD_FILE"
  exit 1
fi

if [ ! -f "$PROGRESS_FILE" ]; then
  echo "Error: Progress file not found: $PROGRESS_FILE"
  exit 1
fi

ITERATIONS=$1

for ((i=1; i<=ITERATIONS; i++)); do
  echo ""
  echo "Iteration $i/$ITERATIONS"
  echo "--------------------------------"
  claude --dangerously-skip-permissions -p "@$PRD_FILE @$PROGRESS_FILE \
1. Find the highest-priority feature to work on and work only on that feature. \
This should be the one YOU decide has the highest priority - not necessarily the first in the list. \
2. Check that the types check via npm run typecheck and that the tests pass via npm run test. \
3. Update the PRD with the work that was done. \
4. Append your progress to the progress.txt file. \
Use this to leave a note for the next person working in the codebase. \
5. Make a git commit of that feature. \
ONLY WORK ON A SINGLE FEATURE. \
If, while implementing the feature, you notice the PRD is complete, output <promise>COMPLETE</promise>. \
" 2>&1 | tee /tmp/ralph_iteration_${i}.log

  result=$(cat /tmp/ralph_iteration_${i}.log)

  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    echo "PRD complete, exiting."
    tt notify "CVM PRD complete after $i iterations"
    exit 0
  fi
done