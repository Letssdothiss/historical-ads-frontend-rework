import uvicorn

# Config
APP_HOST = "0.0.0.0"
APP_PORT = 8083
APP_MODULE = "app.main:app"

if __name__ == "__main__":
    uvicorn.run(APP_MODULE, host=APP_HOST, port=APP_PORT, reload=True)
