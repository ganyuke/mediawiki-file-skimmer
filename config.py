from pydantic import BaseModel, TypeAdapter, ValidationError

class Config(BaseModel):
    base_url: str = "https://test.wikipedia.beta.wmflabs.org"
    wiki_path: str = "/wiki"
    api_path: str = "/w/api.php"
    bot_username: str = "Hoshiyomi@Hololive"
    bot_password: str = "i-love-suisei"

class AppConfig:
    config: Config
    COMMON_PATHS: list[str] = [
        "./config.json"
    ]

    def _read_config(self, path: str) -> Config | None:
        try:
            with open(path, 'r') as f:
                data = f.read()
                return Config.model_validate_json(data)
        except (FileNotFoundError, ValidationError) as e:
            print(e)
            return None
   
    def _load_config(self) -> Config | None:
        config: Config | None = None
        for path in self.COMMON_PATHS:
            config = self._read_config(path)
        return config

    def _create_new_config(self):
        defaultConf = Config()
        with open(self.COMMON_PATHS[0], 'xb') as f:
            adapter = TypeAdapter(Config)
            jsonByes = adapter.dump_json(defaultConf)
            _ = f.write(jsonByes)

        return defaultConf

    def __init__(self):
        self.config = self._load_config() or self._create_new_config()

    def get_wiki_url(self):
        return self.config.base_url + self.config.wiki_path

    def get_api_url(self):
        return self.config.base_url + self.config.api_path