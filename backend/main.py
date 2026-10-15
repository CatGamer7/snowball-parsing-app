import uvicorn
from fastapi import FastAPI

from config import HOST, PORT

app = FastAPI(title="snowball-parsing-app")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)