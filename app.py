"""Entrypoint. `flask --app app run` or `python app.py`."""
from tombot import create_app
from tombot.cli import register as register_cli
from tombot.config import Config

app = create_app(Config)
register_cli(app)


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
