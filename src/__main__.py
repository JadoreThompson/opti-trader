import uvicorn

def main():
    uvicorn.run("server.app:app", port=80, reload=True)


if __name__ == "__main__":
    main()