from fastapi import FastAPI

app = FastAPI(
    title="AI-Powered Personal Productivity Assistant",
    version="0.1.0",
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Personal Productivity Assistant is running."
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok"
    }