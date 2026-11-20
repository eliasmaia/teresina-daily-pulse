cat << 'EOF' > GEMINI.md
# Diretrizes do Projeto: Teresina News Audio AI
- O projeto consome portais de notícias locais de Teresina/PI (Cidade Verde, G1 Piauí, Prefeitura).
- Utiliza Python, FastAPI, Gemini API para resumo e edge-tts para geração de áudio (.mp3).
- O Spotify atua apenas como endpoint final de consumo de RSS/Podcast.
- Código limpo, modular, com tratamento robusto de erros e logs claros no terminal.
- Sempre execute comandos Python e pip utilizando o interpretador do ambiente virtual: `./venv/bin/python` e `./venv/bin/pip`.
EOF