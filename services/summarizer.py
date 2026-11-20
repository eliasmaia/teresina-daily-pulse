import json
import os
from typing import Dict, List
from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel, Field
from datetime import datetime
from zoneinfo import ZoneInfo

WEEKDAYS_PT = {
    0: "segunda-feira",
    1: "terça-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sábado",
    6: "domingo",
}

MONTHS_PT = {
    1: "janeiro",
    2: "fevereiro",
    3: "março",
    4: "abril",
    5: "maio",
    6: "junho",
    7: "julho",
    8: "agosto",
    9: "setembro",
    10: "outubro",
    11: "novembro",
    12: "dezembro",
}


def _format_current_date_pt() -> str:
    now = datetime.now(ZoneInfo("America/Fortaleza"))
    weekday = WEEKDAYS_PT[now.weekday()]
    month = MONTHS_PT[now.month]
    return f"{weekday}, {now.day} de {month} de {now.year} ({now.strftime('%H:%M')})"

def _build_prompts(articles: List[Dict[str, str]]) -> tuple[str, str]:
    current_date_str = _format_current_date_pt()

    formatted_news = "\n\n".join(
        f"TÓPICO {idx} (Fonte: {item['source']}):\n"
        f"Título: {item['title']}\n"
        f"Conteúdo: {item.get('summary', 'N/A')[:500]}"
        for idx, item in enumerate(articles, 1)
    )

    system_instruction = (
        "Você é um âncora de rádio jornalístico local de Teresina, Piauí, apresentando o boletim 'Teresina Daily Pulse'. "
        f"Data e hora de referência desta edição: {current_date_str}. "
        "Use sempre essa data real como referência temporal para dizer 'hoje', 'ontem' ou citar o dia da semana correto no título e no roteiro. "
        "Sua tarefa é transformar os tópicos consolidados em um boletim informativo detalhado, "
        "com aproximadamente 4 a 5 minutos de leitura em voz alta (450 a 600 palavras no campo audio_script).\n\n"
        "Regras editoriais obrigatórias:\n"
        "1. FIDELIDADE ESTRITA AOS FATOS (ZERO INVENÇÃO): Baseie-se EXCLUSIVAMENTE nas informações explicitamente fornecidas nos tópicos. "
        "NUNCA invente horários, eventos, programação cultural, declarações ou justificativas judiciais que não estejam escritos no texto.\n"
        "2. NOMES EXPLÍCITOS DE EMISSORAS, ÓRGÃOS E LOCAIS: Nunca use termos vagos como 'a TV local', 'uma emissora' ou 'um órgão'. "
        "Sempre cite o nome exato da emissora (ex: 'TV Cidade Verde'), instituição, bairro/zona de Teresina ou município piauiense informado na matéria.\n"
        "3. CURADORIA DE SERVIÇO PÚBLICO: Quando houver pautas oficiais, destaque obras, mobilidade, cultura gratuita e cursos profissionalizantes.\n"
        "4. FORMATO DE LOCUÇÃO (audio_script): Escreva APENAS texto falado limpo. Não use Markdown (sem **, #, listas ou colchetes), "
        "não coloque URLs e não escreva rubricas como 'Locutor:' ou '[Vinheta]'.\n"
        "5. TRANSIÇÕES: Conecte os assuntos naturalmente, abrindo com uma saudação rápida e encerrando de forma objetiva."
        "6. COBERTURA E COMPLETUDE: Inclua entre 7 e 10 tópicos no boletim sempre que houver variedade suficiente nos dados recebidos, "
        "dando atenção especial a ocorrências policiais graves, decisões judiciais, saúde, mobilidade e fatos de grande impacto local "
        "sem descartá-los em favor de notas menores. Mantenha também a cobertura de fatos interessantes do esporte, tanto local, quanto os de" \
        "grande importancia nacionalmente"
        "7. SOBRIEDADE EM SEGURANÇA PÚBLICA: Ao noticiar crimes, homicídios ou acidentes, informe apenas o fato essencial "
        "(ocorrência, local e atuação das autoridades). Evite descrições gráficas, cruéis ou sensacionalistas sobre a dinâmica da violência."
    )

    prompt = (
        f"Data de hoje: {current_date_str}.\n"
        f"Gere o boletim estruturado de hoje com base nestes tópicos:\n\n{formatted_news}"
    )
    return system_instruction, prompt
load_dotenv()

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
]


class NewsSegment(BaseModel):
    category: str = Field(description="Categoria: Infraestrutura, Segurança, Política, Economia, Saúde ou Cidade")
    location: str = Field(description="Bairro/zona de Teresina ou município exato do Piauí citado na matéria")
    headline: str = Field(description="Manchete curta e objetiva do fato")
    sources: List[str] = Field(description="Portais que noticiaram este fato")


class DailyBulletin(BaseModel):
    episode_title: str = Field(description="Título atrativo e jornalístico para o episódio do podcast de hoje")
    segments: List[NewsSegment] = Field(description="Lista estruturada dos tópicos abordados no boletim")
    audio_script: str = Field(
        description=(
            "Texto corrido exclusivo para leitura em voz alta (450 a 600 palavras), SEM markdown, "
            "SEM asteriscos, SEM hashtags, SEM URLs e SEM rubricas como 'Locutor:'."
        )
    )



def _pick_groq_model(groq_client: OpenAI) -> str:
    """Busca na API do Groq um modelo de chat ativo para fallback."""
    models = [m.id for m in groq_client.models.list().data]
    for preferred in ("llama-3.3-70b-specdec", "llama-3.1-8b-instant", "qwen/qwen3-32b", "openai/gpt-oss-120b"):
        if preferred in models:
            return preferred
    # Pega qualquer modelo que não seja whisper/guard/tts
    chat_models = [m for m in models if not any(x in m.lower() for x in ("whisper", "guard", "tts", "embed"))]
    if chat_models:
        return chat_models[0]
    raise RuntimeError(f"Nenhum modelo de chat disponível no Groq. Lista: {models}")


def generate_structured_bulletin(articles: List[Dict[str, str]]) -> DailyBulletin:
    """
    Gera o boletim estruturado (Pydantic) via Gemini Structured Outputs,
    com fallback automático para Groq JSON Mode.
    """
    if not articles:
        return DailyBulletin(
            episode_title="Teresina Daily Pulse — Sem atualizações",
            segments=[],
            audio_script="Nenhuma notícia disponível para gerar o boletim de hoje.",
        )

    system_instruction, prompt = _build_prompts(articles)
    last_error = None

    # 1. Tenta Gemini com Structured Output nativo
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        client = genai.Client(
            api_key=gemini_key,
            http_options=types.HttpOptions(timeout=35_000),
        )
        for model_name in GEMINI_MODELS:
            try:
                print(f"   Tentando Gemini Structured Output ({model_name})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3,
                        response_mime_type="application/json",
                        response_schema=DailyBulletin,
                    ),
                )
                return DailyBulletin.model_validate_json(response.text)
            except Exception as exc:
                print(f"   [Aviso] {model_name} falhou ({type(exc).__name__}: {exc})")
                last_error = exc

    # 2. Fallback para Groq em JSON Mode
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            groq_client = OpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=25.0,
            )
            groq_model = _pick_groq_model(groq_client)
            print(f"   Acionando fallback Groq JSON Mode ({groq_model})...")
            schema_hint = json.dumps(DailyBulletin.model_json_schema(), ensure_ascii=False)
            completion = groq_client.chat.completions.create(
                model=groq_model,
                messages=[
                    {
                        "role": "system",
                        "content": f"{system_instruction}\n\nResponda ESTRITAMENTE em JSON válido seguindo este schema:\n{schema_hint}",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return DailyBulletin.model_validate_json(completion.choices[0].message.content)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Todos os provedores falharam. Último erro: {last_error}")


if __name__ == "__main__":
    from scraper import get_all_teresina_news
    from deduplicator import deduplicate_articles

    print("1. Coletando notícias dos 3 portais...")
    raw_news = get_all_teresina_news()
    print(f"   Total bruto coletado: {len(raw_news)} matérias.\n")

    print("2. Agrupando notícias repetidas via Embeddings...")
    unique_topics = deduplicate_articles(raw_news, similarity_threshold=0.82, max_topics=12)
    print(f"   Total consolidado após deduplicação: {len(unique_topics)} tópicos únicos.\n")

    print("3. Gerando boletim estruturado (Pydantic)...")
    bulletin = generate_structured_bulletin(unique_topics)
    print(f"\n=== EPISÓDIO: {bulletin.episode_title} ===")
    for seg in bulletin.segments:
        print(f" - [{seg.category}] ({seg.location}) {seg.headline} | Fontes: {', '.join(seg.sources)}")
    print("\n--- ROTEIRO DE ÁUDIO ---\n")
    print(bulletin.audio_script)