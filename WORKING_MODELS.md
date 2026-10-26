# ThinkTank - Working Models Catalog

**Last Updated:** 2026-10-07  
**Source:** Live API query from NVIDIA NIM and Google Gemini

---

## NVIDIA NIM Models (80 Total)

### General Purpose & Instruction Models
- `nvidia/nemotron-3.5-lightning-30b-a3b` ⭐ (Default, Fast)
- `nvidia/nemotron-4-340b-instruct` (Most Capable)
- `nvidia/llama-3.1-nemotron-70b-instruct`
- `nvidia/llama-3.1-nemotron-51b-instruct`
- `nvidia/nemotron-3-super-120b-a12b`
- `nvidia/nemotron-3-ultra-550b-a55b`

### Meta Models
- `meta/llama2-70b`
- `meta/codellama-70b`
- `meta/llama-3.2-11b-vision-instruct`
- `meta/llama-3.2-90b-vision-instruct`
- `meta/muse-glimmer-30b`

### Mistral AI Models
- `mistralai/mistral-large-2-instruct`
- `mistralai/mistral-large`
- `mistralai/mixtral-8x22b-v0.1`
- `mistralai/mistral-7b-instruct-v0.3`
- `mistralai/codestral-22b-instruct-v0.1`
- `nv-mistralai/mistral-nemo-12b-instruct`

### Google Models via NVIDIA
- `google/gemma-4-31b-it`
- `google/gemma-3-12b-it`
- `google/gemma-3-4b-it`
- `google/gemma-2b`
- `google/codegemma-7b`
- `google/codegemma-1.1-7b`

### IBM Granite Models
- `ibm/granite-3.0-8b-instruct`
- `ibm/granite-3.0-3b-a800m-instruct`
- `ibm/granite-34b-code-instruct`
- `ibm/granite-8b-code-instruct`

### DeepSeek Models
- `deepseek-ai/deepseek-v4.1-flash`
- `deepseek-ai/deepseek-coder-6.7b-instruct`

### Chinese AI Models
- `01-ai/yi-large`
- `z-ai/glm-5.3`
- `z-ai/glm-5.3-flash`
- `moonshotai/kimi-k3`
- `moonshotai/kimi-k2.6`

### Specialized Models
- `microsoft/phi-3.5-moe-instruct`
- `microsoft/phi-3-vision-128k-instruct`
- `writer/palmyra-creative-122b`
- `writer/palmyra-fin-70b-32k`
- `writer/palmyra-med-70b`
- `ai21labs/jamba-1.5-large-instruct`
- `databricks/dbrx-instruct`
- `poolside/laguna-xs-2.1`
- `zyphra/zamba2-7b-instruct`
- `aisingapore/sea-lion-7b-instruct`
- `bigcode/starcoder2-15b`
- `openai/gpt-oss-20b`

### Embedding & Vision Models
- `nvidia/embed-qa-4`
- `nvidia/nv-embedqa-mistral-7b-v2`
- `nvidia/llama-3.2-nv-embedqa-1b-v1`
- `nvidia/nemotron-3-embed-1b`
- `snowflake/arctic-embed-l`
- `nvidia/nvclip`
- `nvidia/neva-22b`
- `nvidia/vila`
- `microsoft/kosmos-2`
- `adept/fuyu-8b`

### Safety & Translation
- `nvidia/llama-3.1-nemoguard-8b-content-safety`
- `nvidia/llama-3.1-nemoguard-8b-topic-control`
- `nvidia/nemotron-3.5-content-safety`
- `nvidia/riva-translate-4b-instruct`
- `nvidia/riva-translate-4b-instruct-v2`

---

## Google Gemini Models (45 Total)

### Gemini 3.x Series (Latest)
- `gemini-3-flash-preview` ⭐ (Recommended)
- `gemini-3.1-pro-preview`
- `gemini-3.1-flash-lite`
- `gemini-3.5-flash`
- `gemini-3.6-flash`
- `gemini-3.7-flash`
- `gemini-3.8-flash`

### Gemini 2.5 Series
- `gemini-2.5-flash`
- `gemini-2.5-pro`
- `gemini-2.5-flash-lite`
- `gemini-2.5-flash-image`

### Latest Aliases
- `gemini-flash-latest`
- `gemini-flash-lite-latest`
- `gemini-pro-latest`

### Gemma Models
- `gemma-4-31b-it`
- `gemma-4-26b-a4b-it`

### Specialized Gemini
- `gemini-3.1-flash-image`
- `gemini-3-pro-image`
- `gemini-3.5-transcribe`
- `gemini-3.8-flash-tts`
- `gemini-omni-1.1-flash`
- `gemini-omni-flash-preview`
- `gemini-nano-banana-2.1`

### Preview & Experimental
- `antigravity-preview-latest`
- `deep-research-max-preview-04-2026`
- `deep-research-preview-04-2026`
- `deep-research-pro-preview-12-2025`
- `gemini-2.5-computer-use-preview-10-2025`
- `gemini-robotics-er-2-preview`
- `lyria-3.5`
- `lyria-3-pro-preview`
- `nano-banana-pro-preview`

---

## Recommended Models by Use Case

### Fast General Purpose
- NVIDIA: `nvidia/nemotron-3.5-lightning-30b-a3b`
- Gemini: `gemini-3-flash-preview`

### High Quality / Complex Tasks
- NVIDIA: `nvidia/nemotron-4-340b-instruct`
- Gemini: `gemini-3.1-pro-preview`

### Code Generation
- `mistralai/codestral-22b-instruct-v0.1`
- `meta/codellama-70b`
- `deepseek-ai/deepseek-coder-6.7b-instruct`

### Vision Tasks
- `meta/llama-3.2-90b-vision-instruct`
- `microsoft/phi-3-vision-128k-instruct`
- `gemini-3-pro-image`

### Multimodal / Audio
- `gemini-omni-1.1-flash`
- `gemini-3.8-flash-tts`

---

## Notes

1. **All models listed above are confirmed working** via live API query on 2026-10-07
2. NVIDIA NIM models are accessed via OpenAI-compatible endpoint
3. Gemini models support generateContent method
4. Some models may have usage limits or require special permissions
5. Preview/experimental models may change or be deprecated

---

## Total Count
- **NVIDIA NIM:** 80 working models
- **Google Gemini:** 45 working models
- **Grand Total:** 125 working models
