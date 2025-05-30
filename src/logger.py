def log_to_file(entry: str):
    with open("app.log", "a") as f:
        _ = f.write(entry)