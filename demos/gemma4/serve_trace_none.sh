#!/usr/bin/env bash
# Experiment: serve gemma4-12B with decode/prefill tracing DISABLED.
# If output is coherent => the trace path is the bug (clears #45763 + #46202).
# Runs entirely inside the tt-build container (localhost, no host networking).
set -uo pipefail

source python_env/bin/activate
cd /work/third_party/tt-metal

export MESH_DEVICE=P150
export VLLM_PLUGINS=tt,tt_model_registry
export HF_HUB_OFFLINE=1
DIR=/work/.cache/models/gemma-4-12B-it
PORT=8009
TRACE_MODE="${1:-none}"   # none | decode_only | all
LOG="/tmp/vllm_serve_trace_${TRACE_MODE}.log"
echo "== trace_mode = ${TRACE_MODE} =="

echo "== vllm version / source =="
python -c "import vllm, vllm.v1.core.kv_cache_utils as m; print('vllm', vllm.__version__); print('src', m.__file__)" 2>&1 | tail -3

echo "== launching vllm serve (trace_mode=none) =="
vllm serve "$DIR" \
  --served-model-name gemma12b \
  --max-num-seqs 1 --max-model-len 4096 --block-size 64 \
  --no-enable-prefix-caching \
  --port "$PORT" \
  --additional-config "{\"tt\": {\"trace_mode\": \"${TRACE_MODE}\"}}" \
  > "$LOG" 2>&1 &
SERVER_PID=$!

echo "== waiting for /health (server pid $SERVER_PID) =="
HEALTHY=0
for i in $(seq 1 150); do      # up to 25 min
  if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    echo "HEALTHY after ~$((i*10))s"; HEALTHY=1; break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "!! SERVER PROCESS DIED before becoming healthy"; break
  fi
  sleep 10
done

if [ "$HEALTHY" = "1" ]; then
  echo "== POST /v1/completions  prompt='The capital of France is'  (greedy) =="
  curl -s "http://localhost:${PORT}/v1/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model":"gemma12b","prompt":"The capital of France is","max_tokens":16,"temperature":0}'
  echo
  echo "== POST /v1/chat/completions  (chat template) =="
  curl -s "http://localhost:${PORT}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model":"gemma12b","messages":[{"role":"user","content":"What is the capital of France?"}],"max_tokens":16,"temperature":0}'
  echo
fi

echo "== ORDERED trace/warmup/alloc markers (line# : text) =="
grep -nE "Warming up|begin_trace|end_trace|capture|active trace|unsafe|corrupted|Starting decode|Finished prefill|Prefill seq len|GEMMA4DBG|_persistent_per_layer|allocate.*page_table|trace_id" "$LOG" | head -120
echo
echo "== context around the allocator warning =="
grep -n "unsafe due to the existence" "$LOG" | head
grep -nB6 -A2 "unsafe due to the existence" "$LOG" | head -40

echo "== shutting down server =="
kill "$SERVER_PID" 2>/dev/null
wait "$SERVER_PID" 2>/dev/null
echo "== DONE =="
