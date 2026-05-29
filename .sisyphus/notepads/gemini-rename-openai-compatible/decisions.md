# Decisions

- GeminiModelConfig → OpenAICompatibleModelConfig (rename, not delete+add)
- GeminiChatProvider → OpenAICompatibleChatProvider (rename + file rename)
- gemini.py → openai_compatible.py (file rename)
- base_url default: https://api.vectorengine.cn
- GeminiVisionNode class and ref ("ai.gemini_vision.v1") remain unchanged
- No backward compat — old names deleted
