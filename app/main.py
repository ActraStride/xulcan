from fastapi import FastAPI

app = FastAPI(
    title="Xulcan API",              # <--- AQUÍ VA EL NOMBRE
    description="Framework API-first para orquestación de Agentes de IA",
    version="0.1.0"
)

@app.get("/health")
def health():
    return {"status": "ok"}
