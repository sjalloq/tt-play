/**
 * Pi provider extension — routes Pi to the local Blackhole p150 LLM server.
 *
 * Pairs with util/tt-llm-server, which exposes an OpenAI-compatible endpoint on
 * http://localhost:8000/v1 (tt-inference-server vLLM fork). Load it with:
 *
 *   pi -e $TT_ROOT/pi/tt-p150a-provider.ts --provider tt-p150a
 *
 * or via the util/pi-p150a wrapper, which does exactly that.
 *
 * Auth: tt-llm-server runs open by default (no JWT_SECRET), so any non-empty
 * key satisfies the OpenAI SDK. Set TT_LLM_API_KEY to the JWT only if you
 * started the server with JWT_SECRET. Defaults to a dummy.
 *
 * Model id must match what the server reports at /v1/models. The static entry
 * below is the single-p150 Llama-3.1-8B-Instruct config (ctx 65536). If the
 * server reports a different id (e.g. the HF repo path), the async discovery
 * below overrides it when the server is reachable at Pi startup.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const BASE_URL = process.env.TT_LLM_BASE_URL ?? "http://localhost:8000/v1";
const API_KEY = process.env.TT_LLM_API_KEY ?? "tt-p150a-local";

// Single-p150 Llama-3.1-8B-Instruct caps (tt-inference-server model_support).
const CONTEXT_WINDOW = 65536;
const MAX_TOKENS = 4096;

function model(id: string) {
	return {
		id,
		name: `${id} (P150a)`,
		reasoning: false,
		input: ["text"] as const,
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: CONTEXT_WINDOW,
		maxTokens: MAX_TOKENS,
	};
}

export default async function (pi: ExtensionAPI) {
	// Prefer the live id(s) the server advertises; fall back to the known static
	// config if the server isn't up yet (so the provider always appears and
	// `pi --list-models` works even with the card idle).
	let models = [model("Llama-3.1-8B-Instruct")];
	try {
		const ctrl = new AbortController();
		const t = setTimeout(() => ctrl.abort(), 1500);
		const res = await fetch(`${BASE_URL}/models`, {
			headers: { Authorization: `Bearer ${API_KEY}` },
			signal: ctrl.signal,
		});
		clearTimeout(t);
		if (res.ok) {
			const body = (await res.json()) as { data?: Array<{ id: string }> };
			if (body.data?.length) models = body.data.map((m) => model(m.id));
		}
	} catch {
		// Server down at startup — keep the static fallback.
	}

	pi.registerProvider("tt-p150a", {
		name: "Tenstorrent P150a (local vLLM)",
		baseUrl: BASE_URL,
		apiKey: API_KEY,
		api: "openai-completions",
		models,
	});
}
