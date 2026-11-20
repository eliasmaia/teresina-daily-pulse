from fastapi import FastAPI

app = FastAPI(title="Teresina News Pipeline", version="1.0.0")

@app.get("/")
def read_root():
    return {
        "status": "online", 
        "message": "Pipeline de notícias de Teresina operando com sucesso!"
        }

@app.post("/pipeline/run")
def run_pipeline():
    # Aqui vamos implementar o scraper + Gemini + edge-tts nos próximos passos
    return {"message": "Execução da pipeline iniciada (em desenvolvimento)"}