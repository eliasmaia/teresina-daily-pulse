import os
from typing import Dict, List
from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI

load_dotenv()

GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
]

GROQ_MODEL = "llama-3.3-70b-versatile"


def _build_prompts(articles: List[Dict[str, str]]) -> tuple[str, str]:
    formatted_news = "\n\n".join(
        f"NOTÍCIA {idx}:\nTítulo: {item['title']}\nConteúdo: {item.get('summary', 'N/A')}"
        for idx, item in enumerate(articles, 1)
    )

    system_instruction = (
        "Você é um âncora de rádio jornalístico local de Teresina, Piauí, apresentando o boletim 'Teresina Daily Pulse'. "
        "Sua tarefa é transformar as reportagens fornecidas em um boletim informativo detalhado, "
        "com aproximadamente 3 a 4 minutos de leitura em voz alta (cerca de 450 a 600 palavras).\n\n"
        "Regras editoriais obrigatórias:\n"
        "1. PRECISÃO GEOGRÁFICA: Sempre especifique o local exato informado no texto. Se o fato ocorreu em Teresina, "
        "cite o bairro, zona ou ponto de referência (ex: 'no bairro Mocambinho, zona Norte'). Se ocorreu no interior, "
        "cite o nome exato do município piauiense (nunca diga apenas 'no interior do Piauí' ou 'na zona rural do estado' se o município estiver no texto).\n"
        "2. PROFUNDIDADE: Explique o que aconteceu, quem está envolvido, os motivos ou desdobramentos citados na matéria.\n"
        "3. FORMATO DE LOCUÇÃO: Escreva APENAS o texto falado. Não use Markdown (sem asteriscos **, hashtags #, listas ou colchetes), "
        "não coloque URLs e não escreva rubricas como 'Locutor:' ou '[Vinheta]'.\n"
        "4. TRANSIÇÕES: Conecte os assuntos de forma fluida e natural, abrindo com uma saudação rápida e encerrando de forma objetiva."
    )

    prompt = f"Gere o roteiro do boletim de hoje com base nestas notícias:\n\n{formatted_news}"
    return system_instruction, prompt


def generate_news_script(articles: List[Dict[str, str]]) -> str:
    """
    Gera o roteiro do boletim tentando primeiro os modelos Gemini Flash
    e fazendo fallback automático para o Groq (Llama 3.3 70B) em caso de 503/429.
    """
    if not articles:
        return "Nenhuma notícia disponível para gerar o boletim de hoje."

    system_instruction, prompt = _build_prompts(articles)
    last_error = None

    # 1. Tenta Gemini Flash
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        client = genai.Client(
            api_key=gemini_key,
            http_options=types.HttpOptions(timeout=15_000),
        )
        for model_name in GEMINI_MODELS:
            try:
                print(f"   Tentando Gemini ({model_name})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.4,
                    ),
                )
                return response.text.strip()
            except Exception as exc:
                print(f"   [Aviso] {model_name} indisponível ({type(exc).__name__}), tentando próximo...")
                last_error = exc

    # 2. Fallback automático para Groq
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            print(f"   Acionando fallback Groq ({GROQ_MODEL})...")
            groq_client = OpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=20.0,
            )
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
            )
            return completion.choices[0].message.content.strip()
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Todos os provedores falharam. Último erro: {last_error}")


if __name__ == "__main__":
    from scraper import get_cidade_verde_news

    print("1. Coletando notícias do Cidade Verde...")
    news = get_cidade_verde_news(limit=11)
    print(f"   {len(news)} notícias encontradas.\n")

    print("2. Gerando roteiro...")
    script = generate_news_script(news)
    print("\n--- ROTEIRO GERADO ---\n")
    print(script)