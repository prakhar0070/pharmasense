"""
Quick inspector for llm_usage_log.jsonl -- shows every real LLM call made
so far: model, tokens, latency, and cost.
"""
import json

try:
    with open("llm_usage_log.jsonl") as f:
        lines = [json.loads(line) for line in f if line.strip()]
except FileNotFoundError:
    print("No llm_usage_log.jsonl yet -- run llm.py or llm_router.py first.")
    exit()

print(f"Total LLM calls logged: {len(lines)}\n")
total_input = sum(l["input_tokens"] for l in lines)
total_output = sum(l["output_tokens"] for l in lines)
total_cost = sum(l["cost_usd_est"] for l in lines)
avg_latency = sum(l["latency_sec"] for l in lines) / len(lines)

print(f"Total input tokens: {total_input}")
print(f"Total output tokens: {total_output}")
print(f"Total estimated cost: ${total_cost:.6f}")
print(f"Average latency: {avg_latency:.2f}s")
print(f"\nMost recent 5 calls:")
for entry in lines[-5:]:
    print(f"  {entry['model']} | in={entry['input_tokens']} out={entry['output_tokens']} "
          f"| {entry['latency_sec']}s | ${entry['cost_usd_est']:.6f}")
